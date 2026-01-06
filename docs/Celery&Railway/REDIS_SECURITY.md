# Configuración de Seguridad para Redis

## ⚠️ IMPORTANTE

**NUNCA uses Redis sin contraseña en producción**. Redis sin autenticación es una vulnerabilidad crítica de seguridad que permite a cualquiera con acceso a la red ejecutar comandos arbitrarios.

## 📋 Tabla de contenidos

- [Configuración local (desarrollo)](#configuración-local-desarrollo)
- [Configuración en producción](#configuración-en-producción)
- [Configuración con Docker](#configuración-con-docker)
- [Verificación de seguridad](#verificación-de-seguridad)

---

## Configuración local (desarrollo)

### Opción 1: Sin contraseña (SOLO para desarrollo local)

Si Redis está en tu máquina local y no es accesible desde la red:

```bash
# En .env
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

### Opción 2: Con contraseña (recomendado incluso en desarrollo)

1. **Configurar contraseña en Redis:**

Edita `/etc/redis/redis.conf` (o `/usr/local/etc/redis.conf` en Mac):

```conf
# Busca esta línea:
# requirepass foobared

# Descoméntala y cambia la contraseña:
requirepass tu_contraseña_segura_aquí
```

2. **Reinicia Redis:**

```bash
# Linux
sudo systemctl restart redis

# Mac
brew services restart redis
```

3. **Actualiza .env:**

```bash
CELERY_BROKER_URL=redis://:tu_contraseña_segura_aquí@127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://:tu_contraseña_segura_aquí@127.0.0.1:6379/1
```

---

## Configuración en producción

### ✅ Checklist de seguridad

- [ ] Redis DEBE tener contraseña configurada
- [ ] Redis DEBE escuchar solo en localhost o red privada
- [ ] Redis NO debe estar expuesto a internet públicamente
- [ ] Usa contraseñas fuertes (mínimo 32 caracteres alfanuméricos)
- [ ] Considera usar Redis ACL (Redis 6+) para permisos granulares

### Configuración recomendada

1. **Genera una contraseña fuerte:**

```bash
# Genera contraseña aleatoria de 32 caracteres
openssl rand -base64 32
```

2. **Configura Redis (`redis.conf`):**

```conf
# Contraseña obligatoria
requirepass TU_CONTRASEÑA_GENERADA_AQUI

# Solo escucha en localhost (si Redis y Django están en el mismo servidor)
bind 127.0.0.1

# O en red privada (si están en servidores diferentes)
bind 0.0.0.0
protected-mode yes

# Deshabilita comandos peligrosos
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command KEYS ""
rename-command CONFIG ""
rename-command SHUTDOWN ""
rename-command BGSAVE ""
rename-command BGREWRITEAOF ""
rename-command SAVE ""
rename-command DEBUG ""
```

3. **Configura `.env` de producción:**

```bash
# Con IP privada
CELERY_BROKER_URL=redis://:TU_CONTRASEÑA@10.0.1.50:6379/0
CELERY_RESULT_BACKEND=redis://:TU_CONTRASEÑA@10.0.1.50:6379/1

# Con hostname
CELERY_BROKER_URL=redis://:TU_CONTRASEÑA@redis-prod.internal:6379/0
CELERY_RESULT_BACKEND=redis://:TU_CONTRASEÑA@redis-prod.internal:6379/1
```

---

## Configuración con Docker

### docker-compose.yml

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    ports:
      - "127.0.0.1:6379:6379"  # Solo localhost
    volumes:
      - redis_data:/data
    networks:
      - internal

  web:
    build: .
    environment:
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/1
    depends_on:
      - redis
    networks:
      - internal

volumes:
  redis_data:

networks:
  internal:
    driver: bridge
```

### .env para Docker

```bash
REDIS_PASSWORD=tu_contraseña_segura_aquí
CELERY_BROKER_URL=redis://:tu_contraseña_segura_aquí@redis:6379/0
CELERY_RESULT_BACKEND=redis://:tu_contraseña_segura_aquí@redis:6379/1
```

---

## Verificación de seguridad

### 1. Verificar que Redis requiere contraseña

```bash
# Intenta conectar sin contraseña (debe fallar)
redis-cli ping
# Debe mostrar: (error) NOAUTH Authentication required

# Conecta con contraseña (debe funcionar)
redis-cli -a tu_contraseña ping
# Debe mostrar: PONG
```

### 2. Verificar que Django/Celery puede conectarse

```bash
# En el servidor de Django
python manage.py shell

>>> from celery import Celery
>>> app = Celery()
>>> app.config_from_object('django.conf:settings')
>>> result = app.send_task('celery.ping')
>>> result.get(timeout=10)
'pong'
```

### 3. Verificar que Redis no está expuesto públicamente

```bash
# Desde FUERA del servidor, esto NO debe funcionar:
redis-cli -h tu-servidor-publico.com ping
# Debe fallar con timeout o connection refused
```

### 4. Revisar logs de intentos de acceso

```bash
# Ver intentos fallidos en logs de Redis
sudo tail -f /var/log/redis/redis.log | grep "NOAUTH"
```

---

## 🚨 Si Redis fue comprometido

Si descubres que Redis estuvo expuesto sin contraseña:

1. **Acción inmediata:**
   ```bash
   # Detén Redis
   sudo systemctl stop redis

   # Configura contraseña en redis.conf
   sudo nano /etc/redis/redis.conf
   # Agrega: requirepass NUEVA_CONTRASEÑA_FUERTE

   # Reinicia Redis
   sudo systemctl start redis
   ```

2. **Investiga:**
   ```bash
   # Revisa logs para ver qué comandos se ejecutaron
   sudo cat /var/log/redis/redis.log | grep -i "command"

   # Revisa las claves actuales
   redis-cli -a tu_nueva_contraseña KEYS "*"
   ```

3. **Limpia si es necesario:**
   ```bash
   # Si hay datos sospechosos, considera hacer FLUSHALL
   redis-cli -a tu_nueva_contraseña FLUSHALL
   ```

4. **Actualiza credenciales:**
   - Cambia la contraseña de Redis
   - Actualiza `.env` con la nueva contraseña
   - Reinicia Celery workers
   - Revisa otros servicios que usen Redis

---

## 📚 Referencias

- [Redis Security - Official Documentation](https://redis.io/docs/management/security/)
- [Redis ACL Documentation](https://redis.io/docs/management/security/acl/)
- [OWASP Redis Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Redis_Security_Cheat_Sheet.html)
