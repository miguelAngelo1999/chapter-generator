# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['chapter_generator.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Purfview-Whisper-Faster', 'Purfview-Whisper-Faster'),
        ('templates', 'templates'),
        ('static', 'static')
    ],
    hiddenimports=['pysrt'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='ChapterGeneratorStandalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='pen_feather_icon_178247.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ChapterGeneratorStandalone'
)
