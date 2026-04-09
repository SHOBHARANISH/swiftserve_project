import os
import math # Added for module 4
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room # Added for module 3
from flask_migrate import Migrate
from datetime import datetime  # if not already imported
from datetime import datetime


# --- App Initialization ---

app = Flask(__name__)

# Configuration
# IMPORTANT: Replace with your PostgreSQL URI for production 
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///swiftserve.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:shobha@localhost/swiftserve' 
app.config['SECRET_KEY'] = 'your_very_secret_key_here' # Change this!

# Extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'


# NEW: Initialize SocketIO (for real-time features) [cite: 29] ---- added for module 3
migrate = Migrate(app, db) 
socketio = SocketIO(app)



# --- NEW: Haversine Formula Helper ---
def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance in kilometers between two points 
    on the earth (specified in decimal degrees).
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers.
    return c * r

def safe_float(value):
    """Converts a value to float, or returns None if it fails."""
    try:
        return float(value)
    except (TypeError, ValueError,):
        return None
    
# --- Database Models [cite: 29] ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # Roles: 'customer', 'restaurant', 'agent' [cite: 29]
    role = db.Column(db.String(20), nullable=False)

    # Relationship to the Restaurant (for restaurant owners)
    restaurant = db.relationship('Restaurant', back_populates='user', uselist=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class Restaurant(db.Model): # Updating restaurant model for module 4
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    cuisine_type = db.Column(db.String(50), nullable=False)

    # NEW: Geolocation fields (added for module 4)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='restaurant')
    menu_items = db.relationship('MenuItem', back_populates='restaurant', lazy=True, cascade="all, delete-orphan")

    # Helper to serialize for JSON responses (added for module 4)
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'cuisine_type': self.cuisine_type,
            'latitude': self.latitude,
            'longitude': self.longitude,
        }

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)

    # Relationship
    restaurant = db.relationship('Restaurant', back_populates='menu_items')

# Models added for module 2

# --- Database Models ---

# ... (Existing User, Restaurant, MenuItem models) ...

class Order(db.Model): # updating order model for module 3 and 4
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    
    # NEW: Link to the delivery agent (added for module 3)
    agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # Customer details collected at checkout
    customer_name = db.Column(db.String(100), nullable=False)
    customer_address = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    
    # NEW: Customer location at time of order (added for module 4)
    customer_latitude = db.Column(db.Float, nullable=True)
    customer_longitude = db.Column(db.Float, nullable=True)

    total_price = db.Column(db.Float, nullable=False)
    
    # Status: 'Placed', 'Preparing', 'Ready for Pickup', 'Picked Up', 'Delivered', 'Rejected'
    status = db.Column(db.String(30), nullable=False, default='Placed')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # ✅ NEW: Scheduled delivery/pre-booking time
    scheduled_time = db.Column(db.DateTime, nullable=True)

    # Relationships
    customer = db.relationship('User', backref='orders', foreign_keys=[customer_id])
    agent = db.relationship('User', foreign_keys=[agent_id])
    restaurant = db.relationship('Restaurant', backref='orders')
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_item = db.Column(db.Float, nullable=False) # Price at the time of purchase

    # Relationship to get item details
    menu_item = db.relationship('MenuItem')

# --- Flask-Login User Loader ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Custom Decorators ---

def restaurant_required(f):
    """Decorator to ensure user is logged in and is a restaurant owner."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'restaurant':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- New decorator for delivery agents --- added for module 3
def agent_required(f):
    """Decorator to ensure user is logged in and is a delivery agent."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'agent':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions --- added for module 2
def get_cart_details():
    """
    Retrieves cart from session and calculates total price.
    Returns a list of (menu_item, quantity) tuples and the total price.
    """
    cart_items = []
    total_price = 0
    
    # session['cart'] will store { 'item_id': quantity }
    cart = session.get('cart', {})
    
    if not cart:
        return [], 0
        
    for item_id, quantity in cart.items():
        item = MenuItem.query.get(int(item_id))
        if item:
            cart_items.append({'item': item, 'quantity': quantity})
            total_price += item.price * quantity
            
    return cart_items, total_price

# --- Authentication Routes  ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role') # 'customer' or 'restaurant'

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('login'))
        
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Logged in successfully as {user.email}!', 'success')
            
            # Redirect based on role
            if user.role == 'restaurant':
                return redirect(url_for('dashboard'))
            elif user.role == 'agent': # added for module 3
                return redirect(url_for('agent_dashboard')) # NEW: agent dashboard route
            else:
                return redirect(url_for('home'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Customer Browsing Routes  ---

@app.route('/')
@app.route('/home')
def home():
    """Customer-facing page to browse all available restaurants."""
    # restaurants = Restaurant.query.all()
    # return render_template('home.html', restaurants=restaurants)
    """
    Renders the homepage. 
    The page will be empty, and JS will make an API call to populate restaurants.
    """
    return render_template('home.html')

# --- NEW: API Route for Nearby Restaurants --- (added for module 4)

@app.route('/api/nearby-restaurants')
def api_nearby_restaurants():
    """
    Returns a JSON list of nearby restaurants based on user's lat/lon.
    This is called by JavaScript on the homepage.
    """
    try:
        user_lat = float(request.args.get('lat'))
        user_lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid location data'}), 400

    all_restaurants = Restaurant.query.all()
    nearby_restaurants = []
    
    for restaurant in all_restaurants:
        if restaurant.latitude and restaurant.longitude:
            distance = haversine(user_lat, user_lon, restaurant.latitude, restaurant.longitude)
            
            # Define "nearby" as < 10 kilometers
            if distance < 10:
                resto_data = restaurant.to_dict()
                resto_data['distance'] = round(distance, 2)
                nearby_restaurants.append(resto_data)
                
    # Sort restaurants by distance (closest first)
    nearby_restaurants.sort(key=lambda x: x['distance'])
    
    return jsonify(nearby_restaurants)

@app.route('/restaurant/<int:restaurant_id>')
def restaurant_menu(restaurant_id):
    """Customer-facing page to view a specific restaurant's menu."""
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    menu_items = restaurant.menu_items
    return render_template('restaurant_menu.html', restaurant=restaurant, menu_items=menu_items)

# --- Restaurant Management Routes ---

@app.route('/dashboard')
@restaurant_required
def dashboard():
    """
    Main dashboard for restaurant owners.
    Checks if they have a profile, if not, redirects to create one.
    If they do, redirects to manage their menu.
    """
    restaurant = Restaurant.query.filter_by(user_id=current_user.id).first()
    if not restaurant:
        flash('Welcome! Please create your restaurant profile to get started.', 'info')
        return redirect(url_for('create_profile'))
    
    # User has a profile, send them to the menu manager
    return redirect(url_for('manage_menu'))

@app.route('/dashboard/profile', methods=['GET', 'POST'])
@restaurant_required
def create_profile(): # 
    """Route for restaurant owners to create their profile."""
    if Restaurant.query.filter_by(user_id=current_user.id).first():
        # If profile already exists, redirect to edit it
        return redirect(url_for('edit_profile'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        cuisine_type = request.form.get('cuisine_type')

        # --- UPDATE THIS --- added for module 4
        latitude = safe_float(request.form.get('latitude'))
        longitude = safe_float(request.form.get('longitude'))
        # --- END UPDATE ---
        
        new_restaurant = Restaurant(
            name=name,
            address=address,
            cuisine_type=cuisine_type,
            user_id=current_user.id, 
            # --- CRITICAL SAVE TO DB ---
            latitude=latitude, longitude=longitude
        )
        db.session.add(new_restaurant)
        db.session.commit()
        
        flash('Restaurant profile created successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('create_profile.html')

@app.route('/dashboard/profile/edit', methods=['GET', 'POST'])
@restaurant_required
def edit_profile(): # 
    """Route for restaurant owners to edit their profile."""
    restaurant = Restaurant.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        restaurant.name = request.form.get('name')
        restaurant.address = request.form.get('address')
        restaurant.cuisine_type = request.form.get('cuisine_type')
        # --- UPDATE THIS --- added for module 4
        restaurant.latitude = safe_float(request.form.get('latitude'))
        restaurant.longitude = safe_float(request.form.get('longitude'))
        # --- END UPDATE ---

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('manage_menu'))
        
    return render_template('edit_profile.html', restaurant=restaurant)


@app.route('/dashboard/menu', methods=['GET', 'POST'])
@restaurant_required
def manage_menu(): # 
    """
    CRUD hub for Menu Items.
    Allows viewing, adding, editing, and deleting items.
    """
    restaurant = Restaurant.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        # This POST request is for ADDING a new item
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        
        new_item = MenuItem(
            name=name,
            description=description,
            price=price,
            restaurant_id=restaurant.id
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Menu item added successfully!', 'success')
        return redirect(url_for('manage_menu'))
    
    # GET request: display existing items
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant.id).all()
    return render_template('manage_menu.html', restaurant=restaurant, menu_items=menu_items)

@app.route('/dashboard/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@restaurant_required
def edit_menu_item(item_id): # 
    """Edit an existing menu item."""
    item = MenuItem.query.get_or_404(item_id)
    # Security check: ensure the item belongs to the logged-in user's restaurant
    if item.restaurant.user_id != current_user.id:
        flash('You do not have permission to edit this item.', 'danger')
        return redirect(url_for('manage_menu'))
        
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.description = request.form.get('description')
        item.price = float(request.form.get('price'))
        db.session.commit()
        flash('Item updated successfully!', 'success')
        return redirect(url_for('manage_menu'))
    
    return render_template('edit_menu_item.html', item=item)

@app.route('/dashboard/menu/delete/<int:item_id>', methods=['POST'])
@restaurant_required
def delete_menu_item(item_id): # 
    """Delete a menu item."""
    item = MenuItem.query.get_or_404(item_id)
    # Security check
    if item.restaurant.user_id != current_user.id:
        flash('You do not have permission to delete this item.', 'danger')
        return redirect(url_for('manage_menu'))
        
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted successfully!', 'success')
    return redirect(url_for('manage_menu'))

# Adding routes for module 2 would go here

# --- Shopping Cart & Order Routes ---

@app.route('/cart/add/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart(item_id):
    if current_user.role != 'customer':
        flash('Only customers can add items to a cart.', 'danger')
        return redirect(url_for('home'))

    # Get the existing cart from session, or create an empty one
    cart = session.get('cart', {})
    
    item = MenuItem.query.get_or_404(item_id)
    
    # Check if cart is empty or if item is from the same restaurant
    if cart:
        first_item_id = next(iter(cart)) # Get first item_id in cart
        first_item = MenuItem.query.get(int(first_item_id))
        if first_item.restaurant_id != item.restaurant_id:
            flash('You can only order from one restaurant at a time. Clear your cart to add this item.', 'warning')
            return redirect(url_for('restaurant_menu', restaurant_id=item.restaurant_id))
    
    item_id_str = str(item_id)
    quantity = cart.get(item_id_str, 0)
    cart[item_id_str] = quantity + 1
    
    # Save the updated cart back into the session
    session['cart'] = cart
    flash(f'"{item.name}" added to your cart.', 'success')
    return redirect(url_for('restaurant_menu', restaurant_id=item.restaurant_id))

@app.route('/cart')
@login_required
def view_cart():
    cart_items, total_price = get_cart_details()
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart_item(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    if item_id_str in cart:
        try:
            quantity = int(request.form.get('quantity'))
            if quantity > 0:
                cart[item_id_str] = quantity
            elif quantity == 0:
                del cart[item_id_str] # Remove if quantity is 0
            
            session['cart'] = cart
        except ValueError:
            flash('Invalid quantity.', 'danger')
    
    return redirect(url_for('view_cart'))

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    
    if item_id_str in cart:
        del cart[item_id_str]
        session['cart'] = cart
        flash('Item removed from cart.', 'success')
        
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items, total_price = get_cart_details()
    
    if not cart_items:
        flash('Your cart is empty. Add items to checkout.', 'warning')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        # --- 1. Get customer details from form ---
        name = request.form.get('name')
        address = request.form.get('address')
        phone = request.form.get('phone')

        # --- 2. Get customer's location from hidden form fields ---
        try:
            cust_lat = float(request.form.get('customer_latitude'))
            cust_lon = float(request.form.get('customer_longitude'))
        except (TypeError, ValueError):
            cust_lat = None
            cust_lon = None
        
        # --- 3. Validate required fields ---
        if not name or not address or not phone:
            flash('Please fill out all delivery details.', 'danger')
            return redirect(url_for('checkout'))

        # --- 4. Get restaurant_id from first item in cart ---
        first_item_in_cart = cart_items[0]['item']
        restaurant_id = first_item_in_cart.restaurant_id

        # --- 5. Handle scheduled delivery / pre-booking ---
        scheduled_time_str = request.form.get('scheduled_time')  # Get value from form
        if scheduled_time_str:
            scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
        else:
            scheduled_time = None

        # --- 6. Create the Order ---
        new_order = Order(
            customer_id=current_user.id,
            restaurant_id=restaurant_id,
            customer_name=name,
            customer_address=address,
            customer_phone=phone,
            total_price=total_price,
            status='Placed',
            customer_latitude=cust_lat,
            customer_longitude=cust_lon,
            scheduled_time=scheduled_time  # Save the scheduled time
        )
        db.session.add(new_order)
        db.session.commit()  # Commit to get new_order.id
        print("DEBUG: Order created with ID:", new_order.id)

        # --- 7. Create OrderItems ---
        for item_data in cart_items:
            item = item_data['item']
            quantity = item_data['quantity']
            
            order_item = OrderItem(
                order_id=new_order.id,
                menu_item_id=item.id,
                quantity=quantity,
                price_per_item=item.price
            )
            db.session.add(order_item)
        db.session.commit()

        # --- 8. Clear the cart ---
        session.pop('cart', None)

        # --- 9. Emit real-time event to the restaurant ---
        restaurant_room = f"restaurant_{restaurant_id}"
        socketio.emit('new_order', {
            'order_id': new_order.id,
            'customer_name': new_order.customer_name,
            'total': new_order.total_price
        }, room=restaurant_room)

        flash('Order placed successfully!', 'success')
        return redirect(url_for('order_details', order_id=new_order.id))

    # --- GET request: render checkout page ---
    return render_template('checkout.html', cart_items=cart_items, total_price=total_price)

@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Security check: Ensure current user is the customer who placed the order
    # or the restaurant owner who needs to process it.
    if current_user.id != order.customer_id and \
       (current_user.role != 'restaurant' or current_user.restaurant.id != order.restaurant_id):
        flash('You do not have permission to view this order.', 'danger')
        return redirect(url_for('home'))
        
    return render_template('order_details.html', order=order)
    
@app.route('/dashboard/orders')
@restaurant_required
def restaurant_orders():
    """Restaurant dashboard to see and manage incoming orders."""
    restaurant = current_user.restaurant
    
    # Get all orders for this restaurant, newest first
    orders = Order.query.filter_by(restaurant_id=restaurant.id)\
                        .order_by(Order.created_at.desc())\
                        .all()
                        
    return render_template('restaurant_orders.html', orders=orders)

@app.route('/dashboard/order/update/<int:order_id>', methods=['POST'])
@restaurant_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Security check
    if order.restaurant_id != current_user.restaurant.id:
        flash('You do not have permission to update this order.', 'danger')
        return redirect(url_for('restaurant_orders'))
        
    new_status = request.form.get('status')
    if new_status in ['Preparing', 'Ready for Pickup', 'Rejected']:
        order.status = new_status
        db.session.commit()

        # NEW: Emit status update to customer (added for module 3)
        order_room = f"order_{order_id}"
        socketio.emit('status_update', {
            'status': new_status
        }, room=order_room)

        flash(f'Order #{order.id} status updated to "{new_status}".', 'success')
              
    return redirect(url_for('restaurant_orders'))

# --- NEW: Delivery Agent Routes --- (added for module 3)

@app.route('/agent/dashboard')
@agent_required
def agent_dashboard():
    """Show agent all orders that are 'Ready for Pickup' OR assigned to them."""

    # Query for orders that are 'Ready for Pickup' OR where agent_id is the current agent's ID
    orders = Order.query.filter(
        (Order.status == 'Ready for Pickup') | (Order.agent_id == current_user.id)
    ).order_by(Order.created_at.asc()).all()

    return render_template('agent_dashboard.html', orders=orders)

@app.route('/agent/accept/<int:order_id>', methods=['POST'])
@agent_required
def agent_accept_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Check if order is still ready
    if order.status == 'Ready for Pickup':
        order.status = 'Picked Up'
        order.agent_id = current_user.id
        db.session.commit()
        
        # NEW: Emit status update to customer
        order_room = f"order_{order_id}"
        socketio.emit('status_update', {
            'status': 'Picked Up',
            'agent_name': current_user.email.split('@')[0] # Send agent's name
        }, room=order_room)
        
        flash(f'You have accepted order #{order.id}.', 'success')

        # NEW: Redirect to the live delivery tracking page (added for module 4)
        return redirect(url_for('agent_delivery', order_id=order.id))
    else:
        flash(f'Order #{order.id} is no longer available.', 'warning')
        return redirect(url_for('agent_dashboard')) # goes inside else block for module 4
    
# NEW: Agent's live delivery page (added for module 4)
@app.route('/agent/delivery/<int:order_id>')
@agent_required
def agent_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Security check: ensure this agent is assigned to this order
    if order.agent_id != current_user.id:
        flash('You are not assigned to this delivery.', 'danger')
        return redirect(url_for('agent_dashboard'))
        
    return render_template('agent_delivery.html', order=order)

# --- NEW: Agent Confirms Delivery Route --- (added for module 4)

@app.route('/agent/complete_delivery/<int:order_id>', methods=['POST'])
@agent_required
def agent_complete_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    
    # 1. Security check: Must be the assigned agent and status must be 'Picked Up'
    if order.agent_id != current_user.id or order.status != 'Picked Up':
        flash('Cannot confirm delivery. Order status is incorrect or you are not the assigned agent.', 'danger')
        return redirect(url_for('agent_dashboard'))
        
    # 2. Update status and commit
    order.status = 'Delivered'
    db.session.commit()
    
    # 3. Emit final status update to customer
    order_room = f"order_{order_id}"
    socketio.emit('status_update', {
        'status': 'Delivered',
        'message': 'Your order has been successfully delivered!'
    }, room=order_room)
    
    flash(f'Order #{order.id} marked as Delivered! Thank you.', 'success')
    
    # 4. Redirect to dashboard (delivery is complete)
    return redirect(url_for('agent_dashboard'))

# --- NEW: SocketIO Event Handlers --- (added for module 3)

@socketio.on('join_order_room')
def handle_join_order_room(data):
    """Called by customer JS when they load an order page."""
    order_id = data['order_id']
    room = f"order_{order_id}"
    join_room(room)
    print(f'Client joined room: {room}')

@socketio.on('join_restaurant_room')
def handle_join_restaurant_room(data):
    """Called by restaurant JS when they load their order dashboard."""
    restaurant_id = data['restaurant_id']
    room = f"restaurant_{restaurant_id}"
    join_room(room)
    print(f'Restaurant joined room: {room}')

# NEW: Listen for agent's location and broadcast to customer
@socketio.on('agent_location_update')
def handle_agent_location_update(data):
    """
    Received from the agent's browser.
    Broadcasts the location to the customer's room.
    """
    order_id = data['order_id']
    location = {
        'lat': data['lat'],
        'lng': data['lng']
    }
    
    # Broadcast to the specific customer's room
    customer_room = f"order_{order_id}"
    emit('customer_location_update', location, room=customer_room)  

# --- Run the App --- (Updated for module 3 to use SocketIO)

if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    #app.run(debug=True)
    socketio.run(app, debug=True)