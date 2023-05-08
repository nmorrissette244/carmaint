import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///cars.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = db.execute("SELECT * FROM positions WHERE user_id = ?", session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

    # Get price of each position symbol
    prices = {}
    for position in portfolio:
        prices[position['symbol']] = lookup(position['symbol'])['price']

    # Get values of all positions
    total_value = user[0]['cash']

    values = {}
    for position in portfolio:
        values[position['symbol']] = position['quantity'] * lookup(position['symbol'])['price']
        total_value += position['quantity'] * lookup(position['symbol'])['price']

    return render_template("index.html", portfolio=portfolio, user=user, prices=prices, values=values, total=total_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        # If input symbol not found, apologize
        if lookup(request.form.get("symbol")) == None:
            return apology("Symbol not found")

        # If user did not input positive integer, return apology
        try:
            int(request.form.get("shares"))
        except:
            return apology("Share field must be integer", 400)

        if int(request.form.get("shares")) <= 0:
            return apology("Share field must be greater than zero", 400)

        # If user does not have enough funds, apologize
        user_funds = float((db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"]))[0]["cash"])
        price = float(lookup(request.form.get("symbol"))["price"])
        cost = price * float(request.form.get("shares"))
        if cost > user_funds:
            return apology("Insufficient funds")

        # User has enough funds, let's do the txn
        else:
            # Record the transaction
            db.execute("INSERT INTO txns VALUES (?, ?, ?, ?, ?)", session["user_id"], request.form.get("symbol"), request.form.get("shares"), price, datetime.datetime.now())

            # Remove funds from user
            db.execute("UPDATE users SET cash = ? WHERE id = ?", (user_funds - cost), session["user_id"])

            # Update positions db
            # First check if user already owns some of symbol
            positionid = str(session["user_id"]) + request.form.get("symbol")
            if len(db.execute("SELECT * FROM positions WHERE id = ?", positionid)) == 0:
                # Add new position
                db.execute("INSERT INTO positions VALUES (?, ?, ?, ?)", positionid, session["user_id"], request.form.get("symbol"), request.form.get("shares"))
            else:
                # User already owns some, add to current amount owned.
                current = int(db.execute("SELECT quantity FROM positions WHERE id = ?", positionid)[0]["quantity"])
                db.execute("UPDATE positions SET quantity = ? WHERE id = ?", (current + int(request.form.get("shares"))), positionid)
            return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM txns WHERE user_id = ?", session['user_id'])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # If method was get, bring us to form to enter stock symbol
    if request.method == "GET":
        return render_template("quote.html")
    # If method was POST, lookup user entered stock symbol
    else:
        stockquote = lookup(request.form.get("symbol"))
        # If info was found successfully, display it in quoted.html
        if stockquote == None:
            return apology("Stock symbol not found")
        else:
            return render_template("quoted.html", name=stockquote["name"], price=stockquote["price"], symbol=stockquote["symbol"])



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure both passwords were submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must provide password", 400)

        # Ensure both passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        # Ensure username is not already in DB
        elif len(db.execute("SELECT username FROM users WHERE username=?", request.form.get("username"))) != 0:
            return apology("Username already exists", 400)

        # If we made it this far, add new user to DB, log them in, and return to homepage
        else:
            """Add new user"""
            db.execute("INSERT INTO users (username, hash, cash) VALUES (?, ?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")), 10000)
            return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        portfolio = db.execute("SELECT * FROM positions WHERE user_id = ?", session["user_id"])

        #   Create dictionary with keys symbols owned and values number of shares owned
        positions = {}
        for position in portfolio:
            positions[position['symbol']] = position['quantity']

        return render_template("sell.html", positions=positions)
    else:
        # Make sure user has # of shares of symbol to sell
        symbol = request.form.get("symbol")
        quantity = int(request.form.get("shares"))

        shares_owned = int(db.execute("SELECT quantity FROM positions WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]['quantity'])

        if shares_owned < quantity:
            return apology("You do not own enough shares for this transaction", 400)
        else:
            # Add value of sale to user's cash field
            sale_amt = quantity * lookup(symbol)['price']
            current_cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])[0]['cash']

            db.execute("UPDATE users SET cash = ? WHERE id = ?", (current_cash + int(sale_amt)), session['user_id'])

            # Remove quantity of shares from portfolio
            current_shares = db.execute("SELECT quantity FROM positions WHERE user_id = ? AND symbol = ?", session['user_id'], symbol)[0]['quantity']
            db.execute("UPDATE positions SET quantity = ? WHERE user_id = ? AND symbol = ?", (current_shares - quantity), session['user_id'], symbol)

            return redirect("/")
