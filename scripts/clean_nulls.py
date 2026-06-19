#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script para limpiar bytes nulos del archivo reparaciones.py"""

import sys

input_file = 'app/routes/reparaciones.py'
output_file = 'app/routes/reparaciones_clean.py'

try:
    # Leer archivo en modo binario
    with open(input_file, 'rb') as f:
        content = f.read()
    
    # Contar bytes nulos
    null_count = content.count(b'\x00')
    print(f"Bytes nulos encontrados: {null_count}")
    
    # Remover bytes nulos
    clean_content = content.replace(b'\x00', b'')
    
    # Guardar archivo limpio
    with open(output_file, 'wb') as f:
        f.write(clean_content)
    
    print(f"Archivo limpio guardado en: {output_file}")
    print(f"Tamaño original: {len(content)} bytes")
    print(f"Tamaño limpio: {len(clean_content)} bytes")
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
