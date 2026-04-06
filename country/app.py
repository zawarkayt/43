import os
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timezone

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- DB CONFIG ---
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/43country")
# Railway gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "zawarkayt")

db = SQLAlchemy(app)


# ===================== MODELS =====================

class Citizen(db.Model):
    __tablename__ = "citizens"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), default="Гражданин")
    is_founder = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "is_founder": self.is_founder,
            "created_at": self.created_at.strftime("%d.%m.%Y") if self.created_at else ""
        }


class News(db.Model):
    __tablename__ = "news"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    tag = db.Column(db.String(50), default="ОФИЦИАЛЬНО")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "tag": self.tag,
            "date": self.created_at.strftime("%d.%m.%Y") if self.created_at else ""
        }


class EnergyStatus(db.Model):
    __tablename__ = "energy_status"
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default="ok")   # ok | warning | critical
    message = db.Column(db.String(255), default="Электросеть работает штатно")
    production = db.Column(db.Integer, default=1240)
    consumption = db.Column(db.Integer, default=980)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        reserve_pct = round(((self.production - self.consumption) / self.production) * 100) if self.production else 0
        return {
            "status": self.status,
            "message": self.message,
            "production": self.production,
            "consumption": self.consumption,
            "reserve_pct": reserve_pct,
            "updated_at": self.updated_at.strftime("%d.%m.%Y %H:%M") if self.updated_at else ""
        }


class SiteSettings(db.Model):
    __tablename__ = "site_settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, default="")

    def to_dict(self):
        return {"key": self.key, "value": self.value}


# ===================== INIT DB =====================

def seed_defaults():
    """Insert default data if tables are empty."""
    if not Citizen.query.first():
        db.session.add(Citizen(name="Заварка", role="Основатель", is_founder=True))
        db.session.add(Citizen(name="Гражданин_1", role="Инженер"))
        db.session.add(Citizen(name="Гражданин_2", role="Строитель"))

    if not News.query.first():
        db.session.add(News(
            title="43Country официально провозглашено государством",
            body="Сегодня Основатель Заварка объявил о создании суверенного государства в мире Satisfactory.",
            tag="ОФИЦИАЛЬНО"
        ))
        db.session.add(News(
            title="43Energy запускает угольную станцию A-2",
            body="Вторая угольная электростанция введена в эксплуатацию. Суммарная мощность — 1,240 МВт.",
            tag="ЭНЕРГЕТИКА"
        ))

    if not EnergyStatus.query.first():
        db.session.add(EnergyStatus())

    if not SiteSettings.query.filter_by(key="about_text").first():
        db.session.add(SiteSettings(
            key="about_text",
            value="<h2>ИСТОРИЯ</h2><p>43Country — суверенное государство, основанное в мире Satisfactory.</p><h2>ЭКОНОМИКА</h2><p>Основа экономики — переработка металлов и производство компонентов.</p><h2>УПРАВЛЕНИЕ</h2><p>Государством управляет Основатель — Заварка.</p>"
        ))

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_defaults()


# ===================== MIDDLEWARE =====================

def require_admin():
    """Check admin password from header or JSON body."""
    pw = request.headers.get("X-Admin-Password") or (request.get_json(silent=True) or {}).get("password")
    if pw != ADMIN_PASSWORD:
        abort(401, "Unauthorized")


# ===================== ROUTES — PUBLIC =====================

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/news", methods=["GET"])
def get_news():
    news = News.query.order_by(News.created_at.desc()).all()
    return jsonify([n.to_dict() for n in news])


@app.route("/api/citizens", methods=["GET"])
def get_citizens():
    citizens = Citizen.query.order_by(Citizen.created_at.asc()).all()
    return jsonify([c.to_dict() for c in citizens])


@app.route("/api/energy", methods=["GET"])
def get_energy():
    status = EnergyStatus.query.first()
    return jsonify(status.to_dict())


@app.route("/api/settings/<key>", methods=["GET"])
def get_setting(key):
    s = SiteSettings.query.get(key)
    if not s:
        return jsonify({"value": ""}), 404
    return jsonify(s.to_dict())


# ===================== ROUTES — ADMIN =====================

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Неверный пароль"}), 401


@app.route("/api/admin/news", methods=["POST"])
def create_news():
    require_admin()
    data = request.get_json()
    if not data.get("title") or not data.get("body"):
        return jsonify({"error": "Заполни все поля"}), 400
    news = News(title=data["title"], body=data["body"], tag=data.get("tag", "ОФИЦИАЛЬНО"))
    db.session.add(news)
    db.session.commit()
    return jsonify(news.to_dict()), 201


@app.route("/api/admin/news/<int:nid>", methods=["DELETE"])
def delete_news(nid):
    require_admin()
    news = News.query.get_or_404(nid)
    db.session.delete(news)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/citizens", methods=["POST"])
def create_citizen():
    require_admin()
    data = request.get_json()
    if not data.get("name"):
        return jsonify({"error": "Введи имя"}), 400
    c = Citizen(name=data["name"], role=data.get("role", "Гражданин"))
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route("/api/admin/citizens/<int:cid>", methods=["DELETE"])
def delete_citizen(cid):
    require_admin()
    c = Citizen.query.get_or_404(cid)
    if c.is_founder:
        return jsonify({"error": "Нельзя удалить основателя"}), 403
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/energy", methods=["POST"])
def update_energy():
    require_admin()
    data = request.get_json()
    status = EnergyStatus.query.first()
    if data.get("status"):
        status.status = data["status"]
    if data.get("message"):
        status.message = data["message"]
    if data.get("production") is not None:
        status.production = int(data["production"])
    if data.get("consumption") is not None:
        status.consumption = int(data["consumption"])
    status.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(status.to_dict())


@app.route("/api/admin/settings", methods=["POST"])
def update_setting():
    require_admin()
    data = request.get_json()
    key = data.get("key")
    value = data.get("value", "")
    if not key:
        return jsonify({"error": "Нет ключа"}), 400
    s = SiteSettings.query.get(key)
    if s:
        s.value = value
    else:
        s = SiteSettings(key=key, value=value)
        db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
