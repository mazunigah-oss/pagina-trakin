"""Genera xl/vbaProject.bin (proyecto VBA de Excel) sin Excel, según la especificación MS-OVBA.

El proyecto se escribe solo con el código fuente (sin la caché compilada): el encabezado _VBA_PROJECT indica
versión 0xFFFF, así Excel descarta la caché y compila el código al abrir el archivo.
"""
import struct
import uuid

# ---------------------------------------------------------------- compresión MS-OVBA (2.4.1)


def _comprimir_bloque(datos, ini, fin):
    out = bytearray()
    pos = ini
    while pos < fin:
        i_flag = len(out)
        out.append(0)
        flag = 0
        for bit in range(8):
            if pos >= fin:
                break
            dif = pos - ini
            bits = max((dif - 1).bit_length(), 4) if dif > 0 else 4
            largo_max = (0xFFFF >> bits) + 3
            mejor_largo, mejor_off = 0, 0
            cand = pos - 1
            while cand >= ini:
                largo = 0
                tope = min(largo_max, fin - pos)
                while largo < tope and datos[cand + largo] == datos[pos + largo]:
                    largo += 1
                if largo > mejor_largo:
                    mejor_largo, mejor_off = largo, pos - cand
                    if largo == tope:
                        break
                cand -= 1
            if mejor_largo >= 3:
                token = ((mejor_off - 1) << (16 - bits)) | (mejor_largo - 3)
                out += struct.pack('<H', token)
                flag |= 1 << bit
                pos += mejor_largo
            else:
                out.append(datos[pos])
                pos += 1
        out[i_flag] = flag
    return bytes(out)


def comprimir(datos: bytes) -> bytes:
    out = bytearray(b'\x01')
    for ini in range(0, len(datos), 4096):
        fin = min(ini + 4096, len(datos))
        c = _comprimir_bloque(datos, ini, fin)
        if len(c) > 4096:  # bloque sin comprimir: 4096 bytes (se rellena con ceros, como indica la especificación)
            out += struct.pack('<H', 0x3000 | (4096 + 2 - 3)) + datos[ini:fin].ljust(4096, b'\0')
        else:
            out += struct.pack('<H', 0xB000 | (len(c) + 2 - 3)) + c
    return bytes(out)


# ---------------------------------------------------------------- archivo compuesto (CFB, MS-CFB versión 3)

LIBRE, FIN_CADENA, SECTOR_FAT, SIN_ENTRADA = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF


def _clave(nombre):
    return (len(nombre), nombre.upper())


def cfb(arbol: dict) -> bytes:
    """arbol: {'nombre': bytes (flujo) | dict (almacenamiento)}. Devuelve el archivo compuesto."""
    entradas = [dict(nombre='Root Entry', tipo=5, hijos=[], datos=None)]

    def agregar(nodo, idx_padre):
        for nombre, valor in nodo.items():
            e = dict(nombre=nombre, tipo=1 if isinstance(valor, dict) else 2, hijos=[],
                     datos=None if isinstance(valor, dict) else valor)
            entradas.append(e)
            entradas[idx_padre]['hijos'].append(len(entradas) - 1)
            if isinstance(valor, dict):
                agregar(valor, len(entradas) - 1)
    agregar(arbol, 0)

    # flujos chicos (< 4096) en el mini stream; grandes en sectores normales
    mini = bytearray()
    mini_fat = []
    grandes = []
    for e in entradas:
        if e['tipo'] != 2:
            continue
        d = e['datos']
        if len(d) < 4096:
            e['inicio'] = len(mini) // 64 if d else FIN_CADENA
            n = (len(d) + 63) // 64
            for k in range(n):
                mini_fat.append(e['inicio'] + k + 1 if k < n - 1 else FIN_CADENA)
            mini += d + b'\0' * (n * 64 - len(d))
        else:
            grandes.append(e)

    sectores = []  # lista de bloques de 512 bytes
    fat = []

    def escribir(datos):
        if not datos:
            return FIN_CADENA
        n = (len(datos) + 511) // 512
        ini = len(sectores)
        for k in range(n):
            sectores.append(datos[k * 512:(k + 1) * 512].ljust(512, b'\0'))
            fat.append(ini + k + 1 if k < n - 1 else FIN_CADENA)
        return ini

    for e in grandes:
        e['inicio'] = escribir(e['datos'])
    inicio_mini = escribir(bytes(mini))
    inicio_minifat = escribir(b''.join(struct.pack('<I', x) for x in mini_fat))
    n_minifat = (len(mini_fat) * 4 + 511) // 512

    # árbol de hermanos: árbol binario de búsqueda balanceado por nombre
    for e in entradas:
        e.update(izq=SIN_ENTRADA, der=SIN_ENTRADA, hijo=SIN_ENTRADA)

    def balancear(idxs):
        if not idxs:
            return SIN_ENTRADA
        m = len(idxs) // 2
        raiz = idxs[m]
        entradas[raiz]['izq'] = balancear(idxs[:m])
        entradas[raiz]['der'] = balancear(idxs[m + 1:])
        return raiz
    for e in entradas:
        if e['hijos']:
            e['hijo'] = balancear(sorted(e['hijos'], key=lambda i: _clave(entradas[i]['nombre'])))

    raiz = entradas[0]
    raiz['inicio'], raiz['tamano'] = (inicio_mini if mini else FIN_CADENA), len(mini)
    dir_bytes = bytearray()
    for e in entradas:
        nombre = e['nombre'].encode('utf-16-le') + b'\0\0'
        tamano = e.get('tamano', len(e['datos']) if e['tipo'] == 2 else 0)
        inicio = e.get('inicio', 0) if e['tipo'] != 1 else 0
        dir_bytes += (nombre.ljust(64, b'\0') + struct.pack('<HBBIII', len(nombre), e['tipo'], 1, e['izq'], e['der'],
                                                               e['hijo'])
                      + b'\0' * 16 + b'\0' * 4 + b'\0' * 16 + struct.pack('<IQ', inicio, tamano))
    while len(dir_bytes) % 512:  # entradas vacías
        dir_bytes += b'\0' * 64 + struct.pack('<HBBIII', 0, 0, 0, SIN_ENTRADA, SIN_ENTRADA, SIN_ENTRADA) + b'\0' * 52
    inicio_dir = escribir(bytes(dir_bytes))

    # sectores de la FAT (se cuentan a sí mismos)
    n_fat = 1
    while (len(sectores) + n_fat) > n_fat * 128:
        n_fat += 1
    assert n_fat <= 109
    sectores_fat = list(range(len(sectores), len(sectores) + n_fat))
    fat += [SECTOR_FAT] * n_fat
    fat += [LIBRE] * (n_fat * 128 - len(fat))
    fat_bytes = b''.join(struct.pack('<I', x) for x in fat)
    for k in range(n_fat):
        sectores.append(fat_bytes[k * 512:(k + 1) * 512])

    difat = sectores_fat + [LIBRE] * (109 - n_fat)
    encabezado = (bytes.fromhex('D0CF11E0A1B11AE1') + b'\0' * 16
                  + struct.pack('<HHHHH', 0x003E, 0x0003, 0xFFFE, 9, 6) + b'\0' * 6
                  + struct.pack('<IIIIIIIII', 0, n_fat, inicio_dir, 0, 4096,
                                inicio_minifat if mini_fat else FIN_CADENA, n_minifat, FIN_CADENA, 0)
                  + b''.join(struct.pack('<I', x) for x in difat))
    assert len(encabezado) == 512
    return encabezado + b''.join(sectores)


# ---------------------------------------------------------------- proyecto VBA (MS-OVBA 2.3)

ID_PROYECTO = '{8D807122-0657-42C8-BC6F-4B5FD08031C9}'
# protección "sin contraseña" cifrada con la clave de ID_PROYECTO (proyecto de referencia generado por Excel)
PROTECCION = 'CMG="DBD966ECE4F0E4F0E4F0E4F0"\r\nDPB="5557E86E18E919E919E9"\r\nGC="CFCD72F0961011111111EE"\r\n'
BASE_LIBRO = '0{00020819-0000-0000-C000-000000000046}'
BASE_HOJA = '0{00020820-0000-0000-C000-000000000046}'
REFERENCIAS = [
    ('stdole', '*\\G{00020430-0000-0000-C000-000000000046}#2.0#0#C:\\Windows\\System32\\stdole2.tlb#OLE Automation'),
    ('Office', '*\\G{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}#2.0#0#C:\\Program Files\\Common Files\\Microsoft Shared\\'
               'OFFICE16\\MSO.DLL#Microsoft Office 16.0 Object Library'),
]
CP = 'cp1252'


def _reg(rid, datos=b''):
    return struct.pack('<HI', rid, len(datos)) + datos


def _fuente(nombre, tipo, codigo):
    if tipo == 'modulo':
        cab = f'Attribute VB_Name = "{nombre}"\r\n'
    else:
        base = BASE_LIBRO if tipo == 'libro' else BASE_HOJA
        cab = (f'Attribute VB_Name = "{nombre}"\r\nAttribute VB_Base = "{base}"\r\n'
               'Attribute VB_GlobalNameSpace = False\r\nAttribute VB_Creatable = False\r\n'
               'Attribute VB_PredeclaredId = True\r\nAttribute VB_Exposed = True\r\n'
               'Attribute VB_TemplateDerived = False\r\nAttribute VB_Customizable = True\r\n')
    codigo = codigo.replace('\r\n', '\n').replace('\n', '\r\n')
    if codigo and not codigo.endswith('\r\n'):
        codigo += '\r\n'
    return (cab + codigo).encode(CP)


def proyecto(modulos) -> bytes:
    """modulos: [(nombre, tipo, codigo)] con tipo 'libro' (ThisWorkbook), 'hoja' o 'modulo'."""
    d = bytearray()
    d += _reg(0x01, struct.pack('<I', 1)) + _reg(0x02, struct.pack('<I', 0x409)) + _reg(0x14, struct.pack('<I', 0x409))
    d += _reg(0x03, struct.pack('<H', 1252)) + _reg(0x04, b'VBAProject')
    d += _reg(0x05) + _reg(0x40) + _reg(0x06) + _reg(0x3D)
    d += _reg(0x07, struct.pack('<I', 0)) + _reg(0x08, struct.pack('<I', 0))
    d += struct.pack('<HIIH', 0x09, 4, 0x52671F51, 0x0020)  # VERSION (tamaño fijo 4 + 6 bytes de datos)
    d += _reg(0x0C) + _reg(0x3C)
    for nombre, libid in REFERENCIAS:
        d += _reg(0x16, nombre.encode(CP)) + _reg(0x3E, nombre.encode('utf-16-le'))
        lib = libid.encode(CP)
        d += _reg(0x0D, struct.pack('<I', len(lib)) + lib + struct.pack('<IH', 0, 0))
    d += _reg(0x0F, struct.pack('<H', len(modulos))) + _reg(0x13, struct.pack('<H', 0xFFFF))
    flujos = {}
    for nombre, tipo, codigo in modulos:
        n8, n16 = nombre.encode(CP), nombre.encode('utf-16-le')
        d += _reg(0x19, n8) + _reg(0x47, n16) + _reg(0x1A, n8) + _reg(0x32, n16)
        d += _reg(0x1C) + _reg(0x48) + _reg(0x31, struct.pack('<I', 0)) + _reg(0x1E, struct.pack('<I', 0))
        d += _reg(0x2C, struct.pack('<H', 0xFFFF)) + _reg(0x21 if tipo == 'modulo' else 0x22) + _reg(0x2B)
        flujos[nombre] = comprimir(_fuente(nombre, tipo, codigo))
    d += _reg(0x10)   # Terminator (0x0010) + Reserved (4 bytes en 0); nada después

    lineas = [f'ID="{ID_PROYECTO}"']
    for nombre, tipo, _ in modulos:
        lineas.append(f'Module={nombre}' if tipo == 'modulo' else f'Document={nombre}/&H00000000')
    texto = ('\r\n'.join(lineas) + '\r\nName="VBAProject"\r\nHelpContextID="0"\r\nVersionCompatible32="393222000"\r\n'
             + PROTECCION + '\r\n[Host Extender Info]\r\n&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;'
             '&H00000000\r\n\r\n[Workspace]\r\n'
             + ''.join(f'{n}=0, 0, 0, 0, C\r\n' for n, _, _ in modulos))
    wm = b''.join(n.encode(CP) + b'\0' + n.encode('utf-16-le') + b'\0\0' for n, _, _ in modulos) + b'\0\0'
    vba = {'dir': comprimir(bytes(d)), '_VBA_PROJECT': bytes.fromhex('CC61FFFF000000')}
    vba.update(flujos)
    return cfb({'PROJECT': texto.encode(CP), 'PROJECTwm': wm, 'VBA': vba})


def nuevo_id():
    return '{' + str(uuid.uuid4()).upper() + '}'
