"""Copia solo las carpetas datos/ y resultados/ desde un ZIP o carpeta v3.6.
Uso (Windows): py IMPORTAR_DATOS_V3_6.py "C:\\ruta\\NodaraTech_Observatorio_V3_H3 (2).zip"
No modifica archivos fuente ni toca el respaldo original. Los índices SQLite
se crean de nuevo para evitar problemas de bloqueo al cambiar de equipo.
"""
from __future__ import annotations
import os,sys,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ALLOWED={'datos','resultados'}
IGNORE={'.sqlite3','.sqlite3-wal','.sqlite3-shm','.pyc'}

def copy_stream(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Se crea un archivo temporal antes de mover al destino; nunca pisamos original.
    temp=destination.with_name('.partial_'+destination.name)
    try:
        with temp.open('wb') as target: shutil.copyfileobj(source,target,1024*1024)
        temp.replace(destination)
    finally:
        if temp.exists():temp.unlink()

def destination_for(parts):
    parts=list(parts)
    if not parts or any(p in ('..','') for p in parts):return None
    for i,p in enumerate(parts):
        if p in ALLOWED:
            inner=parts[i:]
            if len(inner)<2:return None
            if any(p.startswith('.') and p not in ('.gitkeep',) for p in inner):return None
            if Path(inner[-1]).suffix.lower() in IGNORE:return None
            dest=ROOT.joinpath(*inner)
            if not dest.resolve().is_relative_to(ROOT.resolve()):return None
            return dest
    return None

def import_zip(path):
    count=0;size=0;skipped=0
    with zipfile.ZipFile(path) as z:
        for member in z.infolist():
            if member.is_dir():continue
            dest=destination_for(Path(member.filename).parts)
            if dest is None:continue
            if dest.exists():skipped+=1;continue
            # fail closed on corrupt or encrypted archives
            with z.open(member) as source:copy_stream(source,dest)
            count+=1;size+=member.file_size
            if count%50==0:print('Importados',count,'archivos... ',flush=True)
    return count,size,skipped

def import_folder(path):
    count=0;size=0;skipped=0
    for root,dirs,files in os.walk(path):
        dirs[:]=[d for d in dirs if d not in ('.venv','node_modules','__pycache__','.git')]
        for fn in files:
            source=Path(root)/fn
            dest=destination_for(source.relative_to(path).parts)
            if dest is None:continue
            if dest.exists():skipped+=1;continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,dest)
            count+=1;size+=source.stat().st_size
    return count,size,skipped

def main():
    if len(sys.argv)!=2:
        print('Uso: py IMPORTAR_DATOS_V3_6.py "RUTA_A_ZIP_O_CARPETA_ORIGINAL"')
        return 2
    path=Path(sys.argv[1]).expanduser()
    if not path.exists():print('No existe el archivo o carpeta:',path);return 2
    print('Solo se copian datos y resultados faltantes. Se conserva el programa FIRETRACE.')
    n,size,skip=import_folder(path) if path.is_dir() else import_zip(path)
    print(f'Importación completada: {n} archivos nuevos, {size/1048576:.1f} MB, {skip} ya existentes.')
    print('Inicia con: py aplicacion\\visor_incendios.py')
    return 0
if __name__=='__main__':raise SystemExit(main())
