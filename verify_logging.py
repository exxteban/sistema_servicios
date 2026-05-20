
import os
import shutil
from app import create_app

# Clean up previous logs if any (for testing)
if os.path.exists('logs/sistema.log'):
    os.remove('logs/sistema.log')
    
app = create_app('default')

if os.path.exists('logs/sistema.log'):
    print("SUCCESS: Log file created.")
    with open('logs/sistema.log', 'r') as f:
        print("Log Content:")
        print(f.read())
else:
    print("FAILURE: Log file not created.")
