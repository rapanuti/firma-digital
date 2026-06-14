# Firma Digital

Sistema web modular para **firma electrónica verificable de documentos PDF**: subir un PDF,
ubicar visualmente un bloque de firma sobre la página, y generar un PDF firmado con un sello
profesional (firma manuscrita + datos + código QR) verificable desde una página pública.

## ⚠️ Qué es y qué no es (importante)

Este sistema produce un **sello visual + un registro de integridad con hash SHA-256**, **no**
una firma criptográfica PAdES/PKI. En concreto:

- El sello (imagen, texto y QR) es información visible y, por sí solo, **es copiable** a otro PDF.
- La garantía real de integridad es el **hash SHA-256** del PDF firmado, guardado en la base de
  datos. La autenticidad se confirma **comparando el hash** del archivo en mano contra el registrado
  (función "verificar por archivo"), no solo comprobando que "el código existe".
- El no repudio fuerte (firma con certificado X.509 / PAdES) está en el **roadmap**, no en este MVP.

## Características

- **Usuarios y roles**: login/logout, perfil, roles administrador y firmante.
- **Perfil de firma**: imagen manuscrita (PNG/JPG validada), C.I., correo, cargo, activo/inactivo.
- **Documentos**: subida de PDF (validado), hash SHA-256 del original, listado/detalle, descarga protegida.
- **Ubicación visual**: visor PDF.js, bloque arrastrable/redimensionable, coordenadas normalizadas.
- **Generación del PDF firmado**: sello (firma + texto + QR) con PyMuPDF, código único, hash del firmado.
- **Verificación pública**: `/verificar/<código>` con estado válida/anulada/no encontrada, C.I.
  enmascarada y comparación de hash por carga de archivo.
- **Auditoría**: bitácora append-only (subida, firma, verificación, anulación) con IP y user-agent.
- **Anulación**: una firma emitida no se modifica; se anula (con motivo) y queda registrada.

## Stack

- **Backend**: Django 5.2 LTS, PostgreSQL, Python 3.12
- **PDF/imagen/QR**: PyMuPDF, Pillow, qrcode
- **Frontend**: HTML + Tailwind CSS + JavaScript + PDF.js
- **Tests**: pytest + pytest-django

## Requisitos

- Python **3.12** (recomendado; 3.14 es demasiado nueva para el stack)
- PostgreSQL en ejecución
- `gh` opcional (para el flujo de issues)

## Instalación local

```bash
# 1. Clonar
git clone https://github.com/rapanuti/firma-digital.git
cd firma-digital

# 2. Entorno virtual
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Dependencias
pip install -U pip
pip install -r requirements.txt

# 4. Variables de entorno
cp .env.example .env
# Generar una SECRET_KEY y pegarla en .env:
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# Ajustar DATABASE_URL en .env si tu usuario/clave de Postgres difiere.

# 5. Base de datos
createdb firma_digital
python manage.py migrate

# 6. Superusuario (también sirve como firmante)
python manage.py createsuperuser

# 7. Servidor de desarrollo
python manage.py runserver
# Abrir http://127.0.0.1:8000
```

### Probar la generación de PDF firmado

La suite de pruebas genera PDFs firmados reales y valida hashes, sello y verificación:

```bash
pytest                 # toda la batería
pytest signing/        # solo la generación de firma
```

## Uso

1. Ingresar en `/accounts/login/`.
2. **Perfil de firma** → subir la imagen de firma manuscrita y los datos.
3. **Documentos** → "Subir documento" (PDF).
4. **Ubicar firma** → arrastrar/redimensionar el bloque → "Guardar posición".
5. **Firmar** → "Generar PDF firmado".
6. Descargar el PDF firmado (con código, QR y hash).
7. El QR/código lleva a `/verificar/<código>`; también se puede verificar subiendo el PDF.

## Estructura

```text
firma_digital/   proyecto (settings, urls)
accounts/        usuario custom, perfil de firma
documents/       Document, validación PDF, hash, ubicación
signing/         Signature, AuditEvent, motor de sello, anulación
verification/    páginas públicas de verificación
templates/  static/  media/(no versionado)
```

## Recomendaciones para producción

### Variables de entorno

```ini
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<clave fuerte y secreta>
DJANGO_ALLOWED_HOSTS=midominio.com
DATABASE_URL=postgres://usuario:clave@host:5432/firma_digital
VERIFICATION_BASE_URL=https://midominio.com
DJANGO_SECURE_SSL=True
DJANGO_CSRF_TRUSTED_ORIGINS=https://midominio.com
```

### Dominio público para el QR (crítico)
`VERIFICATION_BASE_URL` debe ser el **dominio público HTTPS definitivo antes de empezar a firmar**:
la URL del QR queda incrustada en el PDF al momento de firmar; si cambias el dominio después,
los QR ya emitidos dejarán de resolver.

### Archivos estáticos y media
- `python manage.py collectstatic` (con `DEBUG=False` se usa whitenoise comprimido + manifest).
- **Los PDF originales y firmados NO deben servirse como URL pública.** Aquí solo se exponen
  mediante vistas con control de acceso (dueño/admin). En producción guarda `media/` en un volumen
  privado o almacenamiento de objetos (p. ej. S3 con django-storages, sin ACL pública).
- La página de verificación nunca sirve el archivo: muestra metadatos + hash y compara.

### HTTPS
Obligatorio (la verificación y el QR van sobre TLS). Con `DJANGO_SECURE_SSL=True` se activan
redirección a HTTPS, HSTS y cookies seguras. Termina TLS en nginx/Caddy y sirve la app con gunicorn:
```bash
gunicorn firma_digital.wsgi --workers 3 --bind 127.0.0.1:8000
```

### Backups
- Base de datos (fuente de verdad: hashes, códigos, auditoría): `pg_dump` diario, con prueba de restauración.
- Carpeta `media/` (PDFs originales y firmados): respaldo periódico.

### Logs y seguridad
- Logs de aplicación a stdout (journald/contenedor); la auditoría funcional vive en la tabla `AuditEvent`.
- Usuario de BD con privilegios mínimos; mantener dependencias actualizadas.
- Considerar rate-limiting en login y en verificación (django-ratelimit o el proxy inverso).
- Restringir el acceso a `/admin/`.

## Roadmap

- OTP por correo · múltiples firmantes · firma por lotes · plantillas de firma
- **Firma criptográfica PAdES con certificado** (no repudio fuerte; integridad incrustada en el PDF)
