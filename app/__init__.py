from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config
from .auth import init_oauth
from .models import init_db
from .routes import ui_bp, test_results_api, test_results_ui, crash_logs_bp, legacy_unreal_bp, deploy_quest_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    init_oauth(app)
    init_db()
    app.register_blueprint(ui_bp)
    app.register_blueprint(test_results_api, url_prefix="/api")
    app.register_blueprint(test_results_ui)
    app.register_blueprint(crash_logs_bp)
    app.register_blueprint(legacy_unreal_bp)
    app.register_blueprint(deploy_quest_bp)
    return app
