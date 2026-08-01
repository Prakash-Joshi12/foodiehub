import os, uuid, math, json, io, base64, logging
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
import qrcode

# Load environment variables from a local .env file when present (never
# required in production, where real env vars are set by the host/platform).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE=os.path.dirname(os.path.abspath(__file__))
INSTANCE=os.path.join(BASE,"instance")
UPLOADS=os.path.join(BASE,"static","uploads")
os.makedirs(INSTANCE,exist_ok=True); os.makedirs(UPLOADS,exist_ok=True)

# ---------------------------------------------------------------------------
# Environment / real-world configuration
#
# Every value below is driven by an environment variable so the exact same
# codebase can run locally (SQLite, debug on) and in production (Postgres,
# debug off, secure cookies) without code changes. See .env.example for the
# full list and README.md -> "Real-world deployment" for how to set them.
# ---------------------------------------------------------------------------
ENV = os.environ.get("FLASK_ENV", "development")           # "production" in real deployments
IS_PRODUCTION = ENV == "production"

def _database_uri():
    # Render/Railway/Heroku-style Postgres URLs come in as "postgres://";
    # SQLAlchemy 2.x requires the "postgresql://" scheme.
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    return "sqlite:///" + os.path.join(INSTANCE, "foodienepal.db").replace("\\", "/")

app=Flask(__name__,instance_path=INSTANCE)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "foodienepal-change-this-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = _database_uri()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
app.config["UPLOAD_FOLDER"]=UPLOADS
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB upload cap

# Secure cookies automatically once running behind HTTPS in production.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION

if IS_PRODUCTION and app.config["SECRET_KEY"] == "foodienepal-change-this-in-production":
    raise RuntimeError(
        "SECRET_KEY environment variable must be set to a real secret before "
        "running with FLASK_ENV=production. Generate one with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )

logging.basicConfig(level=logging.INFO)
db=SQLAlchemy(app)

PROVINCES=["Koshi","Madhesh","Bagmati","Gandaki","Lumbini","Karnali","Sudurpashchim"]
STATUSES=["Placed","Confirmed","Preparing","Ready","Assigned","Picked Up","On the Way","Delivered","Cancelled"]
STATUS_CSS={"Placed":"s-placed","Confirmed":"s-confirmed","Preparing":"s-preparing","Ready":"s-ready",
            "Assigned":"s-assigned","Picked Up":"s-picked","On the Way":"s-way","Delivered":"s-delivered","Cancelled":"s-cancelled"}

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(120),nullable=False)
    email=db.Column(db.String(160),unique=True,nullable=False); password=db.Column(db.String(255),nullable=False)
    role=db.Column(db.String(30),nullable=False,default="customer"); phone=db.Column(db.String(40))
    address=db.Column(db.String(255)); province=db.Column(db.String(80)); district=db.Column(db.String(80))
    active=db.Column(db.Boolean,default=True); created_at=db.Column(db.DateTime,default=datetime.utcnow)

class Restaurant(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(160),nullable=False)
    owner_id=db.Column(db.Integer,db.ForeignKey("user.id")); province=db.Column(db.String(80))
    district=db.Column(db.String(80)); city=db.Column(db.String(80)); address=db.Column(db.String(255))
    phone=db.Column(db.String(40)); lat=db.Column(db.Float); lng=db.Column(db.Float)
    approved=db.Column(db.Boolean,default=False); image=db.Column(db.String(255))
    owner=db.relationship("User")

class Food(db.Model):
    id=db.Column(db.Integer,primary_key=True); restaurant_id=db.Column(db.Integer,db.ForeignKey("restaurant.id"),nullable=False)
    name=db.Column(db.String(160),nullable=False); description=db.Column(db.Text); category=db.Column(db.String(80))
    price=db.Column(db.Float,nullable=False); available=db.Column(db.Boolean,default=True)
    restaurant=db.relationship("Restaurant",backref="foods")

class Order(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    restaurant_id=db.Column(db.Integer,db.ForeignKey("restaurant.id"),nullable=False)
    delivery_id=db.Column(db.Integer,db.ForeignKey("user.id")); address=db.Column(db.String(255),nullable=False)
    phone=db.Column(db.String(40),nullable=False); customer_lat=db.Column(db.Float); customer_lng=db.Column(db.Float)
    subtotal=db.Column(db.Float,default=0); delivery_fee=db.Column(db.Float,default=0); discount=db.Column(db.Float,default=0)
    total=db.Column(db.Float,default=0); payment_method=db.Column(db.String(50)); payment_status=db.Column(db.String(30),default="Pending")
    status=db.Column(db.String(40),default="Placed"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    customer=db.relationship("User",foreign_keys=[customer_id]); delivery=db.relationship("User",foreign_keys=[delivery_id])
    restaurant=db.relationship("Restaurant"); items=db.relationship("OrderItem",backref="order",cascade="all, delete-orphan")

class OrderItem(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey("order.id"),nullable=False)
    food_id=db.Column(db.Integer,db.ForeignKey("food.id"),nullable=False); quantity=db.Column(db.Integer,nullable=False)
    price=db.Column(db.Float,nullable=False); food=db.relationship("Food")

class Review(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    restaurant_id=db.Column(db.Integer,db.ForeignKey("restaurant.id"),nullable=False); rating=db.Column(db.Integer,nullable=False)
    food_rating=db.Column(db.Integer); delivery_rating=db.Column(db.Integer)
    comment=db.Column(db.Text,nullable=False); photo=db.Column(db.String(255)); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    customer=db.relationship("User"); restaurant=db.relationship("Restaurant")

class ReviewPhoto(db.Model):
    id=db.Column(db.Integer,primary_key=True); review_id=db.Column(db.Integer,db.ForeignKey("review.id"),nullable=False)
    filename=db.Column(db.String(255),nullable=False)
    review=db.relationship("Review",backref=db.backref("photos",cascade="all, delete-orphan"))

class Message(db.Model):
    id=db.Column(db.Integer,primary_key=True); sender_id=db.Column(db.Integer,db.ForeignKey("user.id"))
    recipient_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    target_type=db.Column(db.String(20),default="user")
    subject=db.Column(db.String(160),nullable=False); body=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    sender=db.relationship("User",foreign_keys=[sender_id]); recipient=db.relationship("User",foreign_keys=[recipient_id])

class Payment(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey("order.id"),nullable=False)
    method=db.Column(db.String(40)); reference=db.Column(db.String(120)); amount=db.Column(db.Float)
    status=db.Column(db.String(30),default="Pending"); qr_payload=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    order=db.relationship("Order")

class DeliveryLocation(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey("order.id"),nullable=False)
    delivery_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False); lat=db.Column(db.Float); lng=db.Column(db.Float)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class Notification(db.Model):
    id=db.Column(db.Integer,primary_key=True); recipient_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    title=db.Column(db.String(160)); message=db.Column(db.Text); read=db.Column(db.Boolean,default=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class Activity(db.Model):
    id=db.Column(db.Integer,primary_key=True); actor_id=db.Column(db.Integer,db.ForeignKey("user.id"))
    action=db.Column(db.String(255)); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    actor=db.relationship("User")

def me(): return db.session.get(User,session.get("uid")) if session.get("uid") else None
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not me(): return redirect(url_for("login"))
        return f(*a,**k)
    return w
def roles(*rs):
    def deco(f):
        @wraps(f)
        def w(*a,**k):
            u=me()
            if not u: return redirect(url_for("login"))
            if u.role not in rs: return "Forbidden",403
            return f(*a,**k)
        return w
    return deco
def notify(uid,title,message):
    if uid: db.session.add(Notification(recipient_id=uid,title=title,message=message))
def activity(action, notify_admin=True):
    """Log an activity AND (by default) push a copy to every admin so the
    admin panel's Activity feed and notification bell reflect it in real time."""
    u=me(); db.session.add(Activity(actor_id=u.id if u else None,action=action))
    if notify_admin:
        for a in User.query.filter_by(role="admin").all():
            notify(a.id,"Platform activity",action)

def make_qr_base64(data):
    """Generate a real, scannable demo QR code (PNG) and return it as a base64 string."""
    img=qrcode.make(data,box_size=8,border=3)
    buf=io.BytesIO(); img.save(buf,format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
def haversine(a,b,c,d):
    R=6371; p=math.pi/180
    x=(c-a)*p; y=(d-b)*p
    h=math.sin(x/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin(y/2)**2
    return 2*R*math.asin(math.sqrt(h))
def seed():
    accounts=[
      ("FoodieNepal Admin","admin@foodienepal.com","admin123","admin"),
      ("Demo Customer","customer@foodienepal.com","customer123","customer"),
      ("Demo Delivery","delivery@foodienepal.com","delivery123","delivery"),
      ("Demo Restaurant Owner","owner@foodienepal.com","owner123","restaurant")]
    for n,e,p,r in accounts:
        if not User.query.filter_by(email=e).first(): db.session.add(User(name=n,email=e,password=generate_password_hash(p),role=r))
    db.session.commit()
    owner=User.query.filter_by(email="owner@foodienepal.com").first()
    data=[
      ("Kathmandu Momo House","Bagmati","Kathmandu","Kathmandu",27.7152,85.3123),
      ("Pokhara Food Hub","Gandaki","Kaski","Pokhara",28.2096,83.9856),
      ("Chitwan Jungle Cafe","Bagmati","Chitwan","Bharatpur",27.6766,84.4359),
      ("Patan Newari Kitchen","Bagmati","Lalitpur","Lalitpur",27.6738,85.3250),
      ("Biratnagar Taste House","Koshi","Morang","Biratnagar",26.4525,87.2718),
      ("Butwal Thakali Ghar","Lumbini","Rupandehi","Butwal",27.7006,83.4484)]
    for n,p,d,c,la,lo in data:
        if not Restaurant.query.filter_by(name=n).first():
            db.session.add(Restaurant(name=n,province=p,district=d,city=c,address=f"{c}, Nepal",lat=la,lng=lo,approved=True))
    db.session.commit()
    r=Restaurant.query.filter_by(name="Kathmandu Momo House").first()
    if r and r.owner_id is None: r.owner_id=owner.id
    menus={
      "Kathmandu Momo House":[("Chicken Momo","Momo",220),("Veg Momo","Momo",180),("Chicken Chowmein","Noodles",250)],
      "Pokhara Food Hub":[("Thakali Dal Bhat","Nepali",350),("Buff Momo","Momo",230)],
      "Chitwan Jungle Cafe":[("Jungle Burger","Burger",320)],"Patan Newari Kitchen":[("Newari Khaja Set","Newari",450)],
      "Biratnagar Taste House":[("Biratnagar Biryani","Rice",380)],"Butwal Thakali Ghar":[("Mutton Thakali Set","Nepali",550)]}
    for rn,items in menus.items():
        rr=Restaurant.query.filter_by(name=rn).first()
        for n,cat,price in items:
            if rr and not Food.query.filter_by(restaurant_id=rr.id,name=n).first(): db.session.add(Food(restaurant_id=rr.id,name=n,category=cat,description=f"Fresh {n}",price=price))
    db.session.commit()

def cart_summary():
    rows=[]; total=0.0
    for fid,qty in session.get("cart",{}).items():
        f=db.session.get(Food,int(fid))
        if f:
            line=round(f.price*qty,2)
            rows.append({"id":f.id,"name":f.name,"price":f.price,"qty":qty,"line_total":line,
                         "restaurant":f.restaurant.name,"restaurant_id":f.restaurant_id})
            total+=line
    return rows,round(total,2)

@app.context_processor
def ctx():
    u=me()
    cart_count=sum(int(q) for q in session.get("cart",{}).values()) if session.get("cart") else 0
    unread_count=Notification.query.filter_by(recipient_id=u.id,read=False).count() if u else 0
    return {"user":u,"provinces":PROVINCES,"statuses":STATUSES,"status_css":STATUS_CSS,"cart_count":cart_count,"unread_count":unread_count}

@app.route("/")
def home():
    q=request.args.get("q",""); province=request.args.get("province",""); lat=request.args.get("lat"); lng=request.args.get("lng")
    rs=Restaurant.query.filter_by(approved=True).all()
    if q: rs=[r for r in rs if q.lower() in (r.name+" "+r.city+" "+r.district).lower()]
    if province: rs=[r for r in rs if r.province==province]
    distances={}
    if lat and lng:
        try:
            la,lo=float(lat),float(lng)
            for r in rs:
                distances[r.id]=round(haversine(la,lo,r.lat,r.lng),2) if r.lat and r.lng else 999999
            rs.sort(key=lambda r:distances.get(r.id,999999))
        except: pass
    rating_rows=db.session.query(Review.restaurant_id,func.avg(Review.rating),func.count(Review.id)).group_by(Review.restaurant_id).all()
    ratings={rid:{"avg":round(avg,1),"count":cnt} for rid,avg,cnt in rating_rows}
    return render_template("home.html",restaurants=rs,distances=distances,ratings=ratings,q=q,province=province)

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        email=request.form["email"].lower().strip()
        if User.query.filter_by(email=email).first(): flash("Email already registered"); return redirect(url_for("register"))
        role=request.form.get("role","customer")
        if role not in ["customer","delivery","restaurant"]: role="customer"
        u=User(name=request.form["name"],email=email,password=generate_password_hash(request.form["password"]),role=role,phone=request.form.get("phone"))
        db.session.add(u); db.session.commit()
        db.session.add(Activity(actor_id=u.id,action=f"New {role} account registered: {u.name} ({email})"))
        for a in User.query.filter_by(role="admin").all():
            notify(a.id,"New user registered",f"{u.name} signed up as a {role}.")
        if role=="restaurant":
            r=Restaurant(name=request.form.get("restaurant_name") or u.name+" Restaurant",owner_id=u.id,province=request.form.get("province"),district=request.form.get("district"),city=request.form.get("city"),address=request.form.get("address"),approved=False)
            db.session.add(r); db.session.commit()
            for a in User.query.filter_by(role="admin").all():
                notify(a.id,"New restaurant registration",f"{r.name} is waiting for approval.")
        db.session.commit()
        flash("Registration successful. Login to continue."); return redirect(url_for("login"))
    return render_template("auth.html",register=True)

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=User.query.filter_by(email=request.form["email"].lower().strip()).first()
        if u and u.active and check_password_hash(u.password,request.form["password"]):
            session["uid"]=u.id; activity("Logged in"); db.session.commit(); return redirect(url_for("dashboard"))
        flash("Invalid login")
    return render_template("auth.html",register=False)

@app.route("/logout")
def logout():
    u=me()
    if u:
        db.session.add(Activity(actor_id=u.id,action=f"{u.name} logged out")); db.session.commit()
    session.clear(); return redirect(url_for("home"))

@app.route("/restaurant/<int:rid>")
def restaurant(rid):
    r=db.session.get(Restaurant,rid)
    if not r or not r.approved:return "Restaurant unavailable",404
    reviews=Review.query.filter_by(restaurant_id=rid).order_by(Review.created_at.desc()).all()
    avg_rating=round(sum(rv.rating for rv in reviews)/len(reviews),1) if reviews else None
    foods=Food.query.filter_by(restaurant_id=rid,available=True).all()
    categories=sorted(set(f.category or "Other" for f in foods))
    table_qr=make_qr_base64(url_for("restaurant",rid=rid,_external=True))
    return render_template("restaurant.html",r=r,foods=foods,categories=categories,reviews=reviews,avg_rating=avg_rating,table_qr=table_qr)

@app.route("/cart/add/<int:fid>",methods=["POST"])
@login_required
def add_cart(fid):
    f=db.session.get(Food,fid)
    if not f:return "Food not found",404
    cart=session.setdefault("cart",{})
    cart[str(fid)]=int(cart.get(str(fid),0))+int(request.form.get("qty",1)); session.modified=True
    return redirect(request.referrer or url_for("home"))

@app.route("/cart")
def cart():
    rows=[]; total=0
    for fid,qty in session.get("cart",{}).items():
        f=db.session.get(Food,int(fid))
        if f: rows.append((f,qty,f.price*qty)); total+=f.price*qty
    return render_template("cart.html",rows=rows,total=total)

@app.route("/cart/remove/<int:fid>")
def remove_cart(fid):
    session.get("cart",{}).pop(str(fid),None); session.modified=True; return redirect(url_for("cart"))

@app.route("/cart/update/<int:fid>",methods=["POST"])
@login_required
def update_cart(fid):
    qty=int(request.form.get("qty",1)); cart=session.setdefault("cart",{})
    if qty<=0: cart.pop(str(fid),None)
    else: cart[str(fid)]=qty
    session.modified=True; return redirect(url_for("cart"))

@app.route("/api/cart")
@login_required
def api_cart():
    rows,total=cart_summary()
    return jsonify(items=rows,total=total,count=sum(r["qty"] for r in rows))

@app.route("/api/cart/set",methods=["POST"])
@login_required
def api_cart_set():
    d=request.get_json() or {}
    try:fid=str(int(d.get("fid")));qty=int(d.get("qty",1))
    except:return jsonify(error="Invalid input"),400
    cart=session.setdefault("cart",{})
    if qty<=0: cart.pop(fid,None)
    else:
        f=db.session.get(Food,int(fid))
        if not f:return jsonify(error="Not found"),404
        cart[fid]=qty
    session.modified=True
    rows,total=cart_summary()
    return jsonify(items=rows,total=total,count=sum(r["qty"] for r in rows))

@app.route("/api/notifications/count")
@login_required
def api_notif_count():
    return jsonify(count=Notification.query.filter_by(recipient_id=me().id,read=False).count())

@app.route("/api/notifications/recent")
@login_required
def api_notif_recent():
    ns=Notification.query.filter_by(recipient_id=me().id).order_by(Notification.created_at.desc()).limit(8).all()
    return jsonify([{"id":n.id,"title":n.title,"message":n.message,"read":n.read,
                      "time":n.created_at.strftime("%b %d, %H:%M")} for n in ns])

@app.route("/api/orders/<int:oid>/status_json")
@login_required
def api_order_status(oid):
    o=db.session.get(Order,oid);u=me()
    if not o:return jsonify(error="Not found"),404
    if u.role=="customer" and o.customer_id!=u.id:return jsonify(error="Forbidden"),403
    return jsonify(id=o.id,status=o.status,payment_status=o.payment_status)

@app.route("/checkout",methods=["GET","POST"])
@roles("customer")
def checkout():
    # Build a clean cart and make sure all items belong to one restaurant.
    cart=session.get("cart",{}) or {}
    rows=[]
    restaurant_ids=set()
    total=0.0

    for fid, qty in cart.items():
        try:
            food_id=int(fid)
            quantity=int(qty)
        except (TypeError,ValueError):
            continue
        if quantity < 1:
            continue

        food=db.session.get(Food,food_id)
        if not food or not food.available:
            continue

        rows.append((food,quantity))
        restaurant_ids.add(food.restaurant_id)
        total += float(food.price) * quantity

    if not rows:
        flash("Your cart is empty or the selected food is no longer available.")
        return redirect(url_for("cart"))

    if len(restaurant_ids) != 1:
        flash("Please order from one restaurant at a time. Remove items from other restaurants and try again.")
        return redirect(url_for("cart"))

    restaurant_id=next(iter(restaurant_ids))
    restaurant=db.session.get(Restaurant,restaurant_id)

    if not restaurant or not restaurant.approved:
        flash("This restaurant is currently unavailable.")
        return redirect(url_for("cart"))

    if request.method=="POST":
        address=(request.form.get("address") or "").strip()
        phone=(request.form.get("phone") or "").strip()
        payment_method=(request.form.get("payment_method") or "COD").strip()

        if not address or not phone:
            flash("Please enter your delivery address and phone number.")
            return redirect(url_for("checkout"))

        allowed_payments={"COD","eSewa","Khalti","IMEPay","Fonepay","Card"}
        if payment_method not in allowed_payments:
            payment_method="COD"

        try:
            customer_lat=float(request.form.get("lat") or 0)
            customer_lng=float(request.form.get("lng") or 0)
        except (TypeError,ValueError):
            customer_lat=0.0
            customer_lng=0.0

        delivery_fee=50.0 if total < 1000 else 0.0
        grand_total=total+delivery_fee

        try:
            order=Order(
                customer_id=me().id,
                restaurant_id=restaurant_id,
                address=address,
                phone=phone,
                customer_lat=customer_lat,
                customer_lng=customer_lng,
                subtotal=round(total,2),
                delivery_fee=delivery_fee,
                total=round(grand_total,2),
                payment_method=payment_method,
                payment_status="Pending",
                status="Placed"
            )
            db.session.add(order)
            db.session.flush()

            for food, quantity in rows:
                db.session.add(OrderItem(
                    order_id=order.id,
                    food_id=food.id,
                    quantity=quantity,
                    price=float(food.price)
                ))

            # QR is generated only for eSewa and Khalti.
            # Other payment methods do not get a QR code.
            qr_payload=None
            if payment_method in {"eSewa","Khalti"}:
                qr_payload=f"FOODIENEPAL|{payment_method}|ORDER:{order.id}|AMOUNT:{grand_total:.2f}"

            db.session.add(Payment(
                order_id=order.id,
                method=payment_method,
                amount=round(grand_total,2),
                qr_payload=qr_payload,
                status="Pending"
            ))

            # Notify restaurant owner only if an owner is assigned.
            if restaurant.owner_id:
                notify(restaurant.owner_id,"New customer order",
                       f"Order #{order.id} received. Please confirm and prepare it.")

            # activity() logs this order to every admin's activity feed & notification bell.
            activity(f"Customer {me().name} placed order #{order.id} at {restaurant.name} (Rs. {grand_total:.2f})")

            db.session.commit()
            session["cart"]={}
            session.modified=True

            flash(f"Order #{order.id} placed successfully.")
            return redirect(url_for("orders"))

        except Exception as exc:
            db.session.rollback()
            app.logger.exception("Checkout failed")
            flash("Order could not be placed. Please check your details and try again.")
            return redirect(url_for("checkout"))

    return render_template("checkout.html",total=round(total,2))
@app.route("/orders")
@login_required
def orders():
    u=me()
    if u.role=="customer": os=Order.query.filter_by(customer_id=u.id).order_by(Order.created_at.desc()).all()
    elif u.role=="delivery": os=Order.query.filter((Order.delivery_id==u.id)|(Order.delivery_id==None)).order_by(Order.created_at.desc()).all()
    elif u.role=="restaurant":
        own=Restaurant.query.filter_by(owner_id=u.id).first(); os=Order.query.filter_by(restaurant_id=own.id).all() if own else []
    else: os=Order.query.order_by(Order.created_at.desc()).all()
    return render_template("orders.html",orders=os)

@app.route("/orders/<int:oid>/accept",methods=["POST"])
@roles("delivery")
def accept(oid):
    o=db.session.get(Order,oid)
    if not o:return "Not found",404
    o.delivery_id=me().id;o.status="Assigned"
    notify(o.customer_id,"Delivery partner assigned",f"Delivery partner {me().name} accepted order #{o.id}. You can now track the delivery.")
    activity(f"{me().name} accepted delivery for order #{o.id}")
    db.session.commit();return redirect(url_for("orders"))

@app.route("/orders/<int:oid>/status",methods=["POST"])
@roles("admin","delivery","restaurant")
def status(oid):
    o=db.session.get(Order,oid); s=request.form["status"]
    if s not in STATUSES:return "Invalid status",400
    o.status=s
    if me().role=="delivery":o.delivery_id=me().id
    notify(o.customer_id,"Order status updated",f"Order #{o.id} is now: {s}.")
    if s=="Delivered":o.payment_status="Paid" if o.payment_method=="COD" else o.payment_status
    activity(f"{me().name} updated order #{o.id} to '{s}'")
    db.session.commit();return redirect(url_for("orders"))

ALLOWED_IMAGE_EXT={".jpg",".jpeg",".png",".webp"}

@app.route("/review/<int:rid>",methods=["POST"])
@roles("customer")
def review(rid):
    rating=int(request.form["rating"])
    food_rating=request.form.get("food_rating")
    delivery_rating=request.form.get("delivery_rating")
    rv=Review(customer_id=me().id,restaurant_id=rid,rating=rating,
              food_rating=int(food_rating) if food_rating else None,
              delivery_rating=int(delivery_rating) if delivery_rating else None,
              comment=request.form["comment"])
    db.session.add(rv); db.session.flush()

    # Support multiple photos uploaded with the review (real-world style feedback)
    photos=request.files.getlist("photos")
    for photo in photos:
        if photo and photo.filename:
            ext=os.path.splitext(photo.filename)[1].lower()
            if ext not in ALLOWED_IMAGE_EXT: continue
            fn=uuid.uuid4().hex+secure_filename(photo.filename)
            photo.save(os.path.join(UPLOADS,fn))
            db.session.add(ReviewPhoto(review_id=rv.id,filename=fn))

    restaurant_obj=db.session.get(Restaurant,rid)
    if restaurant_obj.owner_id:
        notify(restaurant_obj.owner_id,"New customer review",f"{me().name} rated your restaurant {rating}/5.")
    activity(f"{me().name} left a {rating}/5 review for {restaurant_obj.name}")
    db.session.commit();return redirect(url_for("restaurant",rid=rid))

@app.route("/dashboard")
@login_required
def dashboard():
    u=me(); unread=Notification.query.filter_by(recipient_id=u.id,read=False).order_by(Notification.created_at.desc()).all()
    messages=Message.query.filter_by(recipient_id=u.id).order_by(Message.created_at.desc()).limit(10).all()
    return render_template("dashboard.html",notifications=unread,messages=messages,
        orders=Order.query.filter((Order.customer_id==u.id)|(Order.delivery_id==u.id)).order_by(Order.created_at.desc()).limit(10).all())

@app.route("/notifications/read/<int:nid>",methods=["POST"])
@login_required
def read_notification(nid):
    n=db.session.get(Notification,nid)
    if n and n.recipient_id==me().id:n.read=True;db.session.commit()
    if request.args.get("ajax"):return jsonify(ok=True)
    return redirect(url_for("dashboard"))

@app.route("/notifications/read_all",methods=["POST"])
@login_required
def read_all_notifications():
    Notification.query.filter_by(recipient_id=me().id,read=False).update({"read":True})
    db.session.commit()
    if request.args.get("ajax"):return jsonify(ok=True)
    return redirect(url_for("dashboard"))

@app.route("/admin")
@roles("admin")
def admin():
    return render_template("admin.html",
        users=User.query.order_by(User.created_at.desc()).all(),
        restaurants=Restaurant.query.all(),
        orders=Order.query.order_by(Order.created_at.desc()).all(),
        activities=Activity.query.order_by(Activity.created_at.desc()).limit(150).all(),
        reviews=Review.query.order_by(Review.created_at.desc()).limit(50).all(),
        deliveries=User.query.filter_by(role="delivery").order_by(User.name).all(),
        owners=User.query.filter_by(role="restaurant").order_by(User.name).all(),
        customers=User.query.filter_by(role="customer").order_by(User.name).all(),
        messages=Message.query.order_by(Message.created_at.desc()).limit(100).all())

@app.route("/admin/restaurant/<int:rid>",methods=["POST"])
@roles("admin")
def approve(rid):
    r=db.session.get(Restaurant,rid);r.approved=not r.approved
    notify(r.owner_id,"Restaurant approval update",f"Your restaurant is now {'approved' if r.approved else 'disabled'}.")
    activity(f"Admin {'approved' if r.approved else 'disabled'} restaurant '{r.name}'",notify_admin=False)
    db.session.commit();return redirect(url_for("admin"))

@app.route("/admin/message",methods=["POST"])
@roles("admin")
def admin_message():
    recipient_id=request.form.get("recipient_id")
    subject=(request.form.get("subject") or "Message from FoodieNepal Admin").strip()
    body=(request.form.get("body") or "").strip()
    if not recipient_id or not body:
        flash("Please choose a recipient and write a message."); return redirect(url_for("admin"))
    recipient=db.session.get(User,int(recipient_id))
    if not recipient:
        flash("Recipient not found."); return redirect(url_for("admin"))
    db.session.add(Message(sender_id=me().id,recipient_id=recipient.id,target_type=recipient.role,subject=subject,body=body))
    notify(recipient.id,subject,body)
    activity(f"Admin sent a message to {recipient.name} ({recipient.role}): \"{subject}\"",notify_admin=False)
    db.session.commit()
    flash(f"Message sent to {recipient.name}.")
    return redirect(url_for("admin"))

@app.route("/admin/broadcast",methods=["POST"])
@roles("admin")
def admin_broadcast():
    target_role=request.form.get("target_role","")
    subject=(request.form.get("subject") or "Announcement from FoodieNepal Admin").strip()
    body=(request.form.get("body") or "").strip()
    if target_role not in ("customer","delivery","restaurant","all") or not body:
        flash("Please choose a valid audience and write a message."); return redirect(url_for("admin"))
    q=User.query if target_role=="all" else User.query.filter_by(role=target_role)
    recipients=[u for u in q.all() if u.role!="admin"]
    for r in recipients:
        db.session.add(Message(sender_id=me().id,recipient_id=r.id,target_type=target_role,subject=subject,body=body))
        notify(r.id,subject,body)
    activity(f"Admin broadcast a message to all {target_role}: \"{subject}\" ({len(recipients)} recipients)",notify_admin=False)
    db.session.commit()
    flash(f"Broadcast sent to {len(recipients)} {target_role} user(s).")
    return redirect(url_for("admin"))

@app.route("/pay/<int:oid>",methods=["GET","POST"])
@roles("customer")
def pay(oid):
    order=db.session.get(Order,oid)
    if not order or order.customer_id!=me().id:
        return "Forbidden",403

    payment=Payment.query.filter_by(order_id=oid).first()
    if not payment:
        flash("Payment record was not found.")
        return redirect(url_for("orders"))

    qr_methods={"eSewa","Khalti"}

    if request.method=="POST":
        reference=(request.form.get("reference") or "").strip()

        if payment.method=="COD":
            payment.status="Pending"
            order.payment_status="Pending"
            db.session.commit()
            flash("Cash on Delivery selected. Payment will be collected on delivery.")
            return redirect(url_for("orders"))

        if not reference:
            flash("Please enter a transaction reference.")
            return redirect(url_for("pay",oid=oid))

        payment.reference=reference
        payment.status="Paid"
        order.payment_status="Paid"

        activity(f"Payment of Rs. {payment.amount:.2f} recorded for order #{oid} via {payment.method} (ref: {reference})")
        db.session.commit()

        flash("Payment recorded successfully.")
        return redirect(url_for("orders"))

    show_qr=payment.method in qr_methods
    qr_b64=make_qr_base64(payment.qr_payload) if show_qr and payment.qr_payload else None
    return render_template(
        "payment.html",
        order=order,
        payment=payment,
        show_qr=show_qr,
        qr_b64=qr_b64
    )

@app.route("/api/restaurants")
def all_restaurants_api():
    return jsonify([
        {"id":r.id,"name":r.name,"lat":r.lat,"lng":r.lng,
         "province":r.province,"city":r.city,
         "url":url_for("restaurant",rid=r.id)}
        for r in Restaurant.query.filter_by(approved=True).all()
        if r.lat is not None and r.lng is not None
    ])

@app.route("/api/restaurants/nearby")
def nearby():
    try:lat=float(request.args["lat"]);lng=float(request.args["lng"]);radius=float(request.args.get("radius",20))
    except:return jsonify({"error":"lat,lng required"}),400
    out=[]
    for r in Restaurant.query.filter_by(approved=True).all():
        if r.lat and r.lng:
            d=haversine(lat,lng,r.lat,r.lng)
            if d<=radius:out.append({"id":r.id,"name":r.name,"lat":r.lat,"lng":r.lng,"distance_km":round(d,2),"url":url_for("restaurant",rid=r.id)})
    return jsonify(sorted(out,key=lambda x:x["distance_km"]))

@app.route("/api/orders/<int:oid>/location",methods=["POST"])
@roles("delivery")
def location(oid):
    o=db.session.get(Order,oid)
    if not o or o.delivery_id!=me().id:return jsonify(error="Forbidden"),403
    d=request.get_json() or {}
    try:lat=float(d["lat"]);lng=float(d["lng"])
    except:return jsonify(error="Invalid coordinates"),400
    db.session.add(DeliveryLocation(order_id=oid,delivery_id=me().id,lat=lat,lng=lng));db.session.commit()
    return jsonify(ok=True,lat=lat,lng=lng)

@app.route("/api/orders/<int:oid>/track")
@roles("customer","admin","delivery","restaurant")
def track(oid):
    o=db.session.get(Order,oid);u=me()
    if not o:return jsonify(error="Not found"),404
    if u.role=="customer" and o.customer_id!=u.id:return jsonify(error="Forbidden"),403
    points=DeliveryLocation.query.filter_by(order_id=oid).order_by(DeliveryLocation.created_at.asc()).all()
    return jsonify(order_id=oid,status=o.status,delivery_id=o.delivery_id,customer_lat=o.customer_lat,customer_lng=o.customer_lng,points=[{"lat":p.lat,"lng":p.lng,"time":p.created_at.isoformat()} for p in points])

@app.route("/api/health")
def health():return jsonify(ok=True,database=os.path.exists(os.path.join(INSTANCE,"foodienepal.db")))

with app.app_context():
    db.create_all()
    seed()

if __name__=="__main__":
    host = os.environ.get("HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0" if IS_PRODUCTION else "1") == "1"
    print(f"FoodieNepal running: http://{('127.0.0.1' if host=='0.0.0.0' else host)}:{port}  (env={ENV})")
    if host == "0.0.0.0":
        print("Also reachable from other devices on your network/LAN at your machine's local IP.")
    app.run(host=host, port=port, debug=debug)
