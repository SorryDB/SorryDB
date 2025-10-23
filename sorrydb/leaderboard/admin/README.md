# Admin Setup

## Initial Admin User

On first startup, an admin user is automatically created using environment variables in compose.yaml:

```yaml
environment:
  - INITIAL_ADMIN_EMAIL=admin@sorrydb.org
  - INITIAL_ADMIN_PASSWORD=changeme
```

## Change Admin Password

**Change the default password immediately after deployment!**

### API Endpoint

```bash
# 1. Get access token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@sorrydb.org&password=changeme"

# 2. Change password (use the token from step 1)
curl -X POST http://localhost:8000/auth/change-password \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -d '{
    "current_password": "changeme",
    "new_password": "NewSecurePassword"
  }'
```

## Admin Panel

Access at: http://localhost:8000/admin/login/
