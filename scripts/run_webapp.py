from app.web.simple_server import run_server


if __name__ == "__main__":
    # Gyanús pont: a jelenlegi Streamlit simple_server.py már nem ad
    # run_server() függvényt. Inkább ezt használd:
    # python -m streamlit run app/web/simple_server.py
    run_server(host="127.0.0.1", port=8000)

# Indítás: python -m scripts.run_webapp
