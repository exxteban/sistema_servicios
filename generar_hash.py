from werkzeug.security import generate_password_hash

# Cambia "MiClave123" por la contraseña que quieras usar
nuevo_hash = generate_password_hash("adminpassdemo")

print(nuevo_hash)
#ultimo pass admin: CLAVEadmin
#ultimo pass demo: demostrac!ion

#UPDATE usuarios SET password_hash = '' WHERE username = 'root';