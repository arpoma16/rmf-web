from os.path import dirname

from api_server.default_config import config

here = dirname(__file__)
run_dir = f"{here}/run"

config.update(
    {
        "host": "0.0.0.0",  # Escuchar en todas las interfaces (importante para Docker)
        "port": 8000,
        "db_url": f"sqlite://{run_dir}/db.sqlite3",
        "cache_directory": f"{run_dir}/cache",  # The directory where cached files should be stored.
        "ros_args": ["-p", "use_sim_time:=true"],
        "log_level": "INFO",
        "timezone": "Asia/Singapore",
    }
)
