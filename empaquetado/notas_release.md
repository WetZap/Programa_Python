## Descargas

No hace falta instalar Python: cada fichero trae todo lo necesario.

| Sistema | Fichero |
|---|---|
| **Windows 10/11** (64 bits) | `…-windows-x64-instalador.exe` (o el `…-portable.zip`, sin instalar) |
| **macOS** con chip Apple (M1, M2…) | `…-macos-arm64.dmg` |
| **macOS** con procesador Intel | `…-macos-x86_64.dmg` |
| **Linux** (x86_64, glibc ≥ 2.35: Ubuntu 22.04+, Debian 12+, Fedora 36+…) | `…-linux-x86_64.AppImage` |

Los ejecutables no están firmados con un certificado de pago, así que el sistema avisa la primera vez:

- **Windows**: «Windows protegió su PC» → *Más información* → *Ejecutar de todas formas*.
- **macOS**: arrastra *ajustelab* a *Aplicaciones* y ábrelo. Si dice que no se puede verificar, ve a *Ajustes del Sistema → Privacidad y seguridad* y pulsa *Abrir igualmente* (solo la primera vez).
- **Linux**: `chmod +x ajustelab-*.AppImage` y ejecútalo. Si falta FUSE (`libfuse2`), ejecútalo con `--appimage-extract-and-run`. Para tenerlo en el menú de aplicaciones: `./ajustelab-*.AppImage --instalar-escritorio`.

`SHA256SUMS.txt` tiene las sumas para comprobar las descargas (`sha256sum -c --ignore-missing SHA256SUMS.txt`).

Con Python instalado también se puede instalar con `pip` o con los instaladores de una línea: ver [Instalación](https://github.com/WetZap/Programa_Python/blob/main/docs/INSTALACION.md).
