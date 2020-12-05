import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).parent.parent))

from api.main import app
import uvicorn

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port="8000")