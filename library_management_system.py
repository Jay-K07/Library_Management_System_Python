import PySimpleGUI as sg  #importing PySimpleGUI to create graphical interface
import sqlite3 #importing sqlite for interacting with databse
import re #importing regular expression library to validate email fields
from datetime import datetime #importing datetime to work with dates and time for late fees
import logging # importing logging to keep track of aplication activities like errors
import json #file handling to store data allowing us to save and load data in to our system

def create_tables(cursor): # creates the tables in sql for the library system
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        quantity INTEGER NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact_info TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        loan_date TEXT NOT NULL,
        return_date TEXT,
        FOREIGN KEY(book_id) REFERENCES books(id),
        FOREIGN KEY(member_id) REFERENCES members(id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT
    )
    """)

# Configuring the logging module
logging.basicConfig(
    level=logging.ERROR,  # Log messages at the ERROR level and above
    format="%(asctime)s - %(levelname)s - %(message)s", # how to show the logged information
    handlers=[ # where to store the logs
        logging.FileHandler("library_system.log"),  # Log to a file
        logging.StreamHandler()  # Also log to console
    ]
)

# Function to connect to the SQLite database
def connect_to_db(db_name="library.db"):
    connection = sqlite3.connect(db_name) # establishing a connection to database
    connection.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints to be able to oull information from other tables
    cursor = connection.cursor() #cursor to interact with database to execute actions
    return connection, cursor # return the connection and cursor to use later

# Function to calculate fines (for late returns)
def calculate_fine(loan_date, return_date=None):
    fine_calculation = 1.00  # Fee per overdue day
    borrow_period = 7  # Borrowing period in days
    return_date = return_date or datetime.now().strftime("%Y-%m-%d") # use todays date if no date given
    loan_date = datetime.strptime(loan_date, "%Y-%m-%d") #converting loan date string to datetime
    return_date = datetime.strptime(return_date, "%Y-%m-%d") #converting return date string to date time
    overdue_days = (return_date - loan_date).days - borrow_period # calculate how many days overdue

    if overdue_days > 0:
        return overdue_days * fine_calculation #calculation of how much is owed for late fee
    return 0.0 # returned within the 14 days

# Admin functions for book and member management
def add_book(cursor, title, author, quantity):
    cursor.execute("INSERT INTO books (title, author, quantity) VALUES (?, ?, ?)", (title, author, quantity))
    cursor.connection.commit() # commit changes to the database

def remove_book(cursor, book_id):
    try:
        # Convert and validate book_id
        book_id = int(book_id)
        if book_id <= 0:
            logging.warning(f"Invalid negative or zero Book ID: {book_id}")
            return False, "Book ID must be a positive number."
        
        # Check if book exists
        cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
            cursor.connection.commit()
            logging.info(f"Book ID {book_id} removed successfully.")
            return True, f"Book ID {book_id} removed successfully."
        else:
            logging.warning(f"Book ID {book_id} not found.")
            return False, f"Book ID {book_id} does not exist."
    except ValueError:
        logging.error(f"Invalid book ID format: {book_id}")
        return False, "Please enter a valid number for Book ID."

def add_member(cursor, name, contact_info):
    cursor.execute("INSERT INTO members (name, contact_info) VALUES (?, ?)", (name, contact_info)) # adding new member in members table with given information
    cursor.connection.commit() # commiting to new members addition
    return cursor.lastrowid  # Return the member ID of newly added member

def remove_member(cursor, member_id):
    try:
        # Convert and validate member_id
        member_id = int(member_id)
        if member_id <= 0:
            logging.warning(f"Invalid negative or zero Member ID: {member_id}")
            return False, "Member ID must be a positive number."
            
        # Check if member exists
        cursor.execute("SELECT id FROM members WHERE id = ?", (member_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
            cursor.connection.commit()
            logging.info(f"Member ID {member_id} removed successfully.")
            return True, f"Member ID {member_id} removed successfully."
        else:
            logging.warning(f"Member ID {member_id} not found.")
            return False, f"Member ID {member_id} does not exist."
    except ValueError:
        logging.error(f"Invalid member ID format: {member_id}")
        return False, "Please enter a valid number for Member ID."

# Function to view all books in the library
def display_books(cursor):
    cursor.execute("SELECT * FROM books") #executes query to view all books by retrieving all records
    return cursor.fetchall() # returns all rows as a list where each tuple is a book record

# Function to borrow a book
def borrow_book(cursor, book_id, member_id):
    try:        
        book_id = int(book_id)
        member_id = int(member_id) # convert inputs to integers for validation and stored in a variable ## if they invalid input is given, a value error will appear        
        loan_date = datetime.now().strftime("%Y-%m-%d") # this uses the current date to be used as the loan date YYYY-MM-DD        
        cursor.execute("SELECT quantity FROM books WHERE id = ?", (book_id,)) # first checks to see if the bookID is in the database by queryiung
        result = cursor.fetchone()        
        if not result:
            logging.warning(f"Attempted to borrow non-existent book ID: {book_id}") # if the query is executed and no bookID is found, a message will be retruned saying that book does not exist whilst also logging it
            return False, "Book ID does not exist in the system."
            
        if result[0] <= 0: # if the book quantity is at 0, it will log that there is none available and someone trie d to borrow the book
            logging.warning(f"Attempted to borrow book ID: {book_id} with no available copies")
            return False, "Book is currently out of stock." # returns an out of stock message - no forward movement          
        cursor.execute("SELECT id FROM members WHERE id = ?", (member_id,)) # makes sure there is a member id that exists has been given when loaning the book
        
        if not cursor.fetchone():
            logging.warning(f"Non-existent member ID: {member_id} attempted to borrow book") # if no id is given there will be an error
            return False, "Member ID is not registered in the system." # message returned
            
        cursor.execute("""
            SELECT id FROM loans 
            WHERE book_id = ? AND member_id = ? AND return_date IS NULL
        """, (book_id, member_id)) # runs a query to see if the member has an eactive loan for the given book already, if they do not, can contine
        
        if cursor.fetchone():
            logging.warning(f"Member ID: {member_id} attempted to borrow book ID: {book_id} which they already have") # if there is an active loan with the same book with the same member thenloan will be cancelled
            return False, "You already have this book borrowed." # message returned
        
        cursor.execute(
            "INSERT INTO loans (book_id, member_id, loan_date) VALUES (?, ?, ?)",
            (book_id, member_id, loan_date) # if the above vhecks are passed, a new loan record will be made using the given ids
        )
        
        cursor.execute(
            "UPDATE books SET quantity = quantity - 1 WHERE id = ?", # this executes a deduction of 1 from the book so it shows in the table
            (book_id,)
        )
        
        # Save changes to database
        cursor.connection.commit()
        logging.info(f"Book ID: {book_id} successfully borrowed by Member ID: {member_id}")
        return True, "Book borrowed successfully!"
        
    except ValueError as e:
        # error message to show for when a invalid input like words are put when expecting a number
        logging.error(f"Invalid input format: {str(e)}")
        return False, "Please enter valid number for Book ID."
    
    except sqlite3.Error as e:
        # Handle database related errors
        logging.error(f"Database error while borrowing book: {str(e)}")
        cursor.connection.rollback()
        return False, "Database error occurred. Please try again."
    
    except Exception as e:
        # Handle any unexpected errors
        logging.error(f"Unexpected error while borrowing book: {str(e)}")
        cursor.connection.rollback()
        return False, "An unexpected error occurred. Please try again."

# Function to return a book
def return_book(cursor, loan_id, return_date):
    try:
        loan_id = int(loan_id) # Convert loan_id to number for validation        
        try:
            datetime.strptime(return_date, "%Y-%m-%d") #validate the date format to avoid crashing the system when an invalid format has been given
        except ValueError:
            logging.error(f"Invalid date format provided: {return_date}") # if invalid date given an error message will show
            return None, "Please enter date in YYYY-MM-DD format."
                    
        # checking if loan exists and book hasn't been returned by querying loans table to make sure the loan id has not had a book returned yet
        cursor.execute("""
            SELECT l.book_id, l.loan_date, l.member_id, b.title  
            FROM loans l
            JOIN books b ON l.book_id = b.id
            WHERE l.id = ? AND l.return_date IS NULL
        """, (loan_id,)) # checks the loans table for the book id, whoo tok it out and when, and checks whether the return date is null
        
        result = cursor.fetchone()
        if not result:
            logging.warning(f"Attempted to return non-existent or already returned loan ID: {loan_id}") # letting you know the book is already returned or incorrect
            return None, "Invalid loan ID or book already returned."
            
        book_id, loan_date, member_id, book_title = result # extracting the result from the query and storing it in a variable
        
        fine = calculate_fine(loan_date, return_date) # calculate any late fees calling the calculate_fine function
        
        cursor.execute("""
            UPDATE loans 
            SET return_date = ?, fee = ? 
            WHERE id = ?
        """, (return_date, fine, loan_id)) # updated loan record with return date and fee
        
        # Update book quantity to reflect the return
        cursor.execute("""
            UPDATE books 
            SET quantity = quantity + 1 
            WHERE id = ?
        """, (book_id,)) # update book quantity to reflect the return by updating the book table
        
        # save changes to database
        cursor.connection.commit()
        
        message = f"Book '{book_title}' returned successfully." # message relaying successful return and that if there is a fine to add the message stating twhat the fine is
        if fine > 0:
            message += f" Late fee: £{fine:.2f}"
            
        logging.info(f"Book ID {book_id} returned successfully. Loan ID: {loan_id}, Fine: £{fine:.2f}") # logging successful return
        return fine, message
        
    except ValueError as e:
        logging.error(f"Invalid loan ID format: {str(e)}") 
        cursor.connection.rollback()
        return None, "Please enter a valid number for Loan ID." # this will show when the loan_id input is not a  number, resetting the change and showing the error message, stopping system from crashing while also logging the error and displaying a message
        
    except sqlite3.Error as e:
        logging.error(f"Database error while returning book: {str(e)}")
        cursor.connection.rollback()
        return None, "Database error occurred. Please try again." # handles any database error, showing an error messaage when this occured, managing the possible error
        
    except Exception as e:
        logging.error(f"Unexpected error while returning book: {str(e)}")
        cursor.connection.rollback()
        return None, "An unexpected error occurred. Please try again." # catches any other unexpected issues and logs the error and returning an error message.

def is_valid_book(cursor, book_id):
    cursor.execute("SELECT COUNT(*) FROM books WHERE id = ?", (book_id,))
    return cursor.fetchone()[0] > 0 # return true if book exists otherwise it would be false

def is_valid_member(cursor, member_id):
    cursor.execute("SELECT COUNT(*) FROM members WHERE id = ?", (member_id,))
    return cursor.fetchone()[0] > 0 # return true if member exists otherwise it would be false

# function to view member's current loans
def view_loans(cursor, member_id=None):
    if member_id:
        cursor.execute("SELECT id, book_id, loan_date, return_date, fee FROM loans WHERE member_id = ?", (member_id,))
    else:
        cursor.execute("SELECT id, book_id, member_id, loan_date, return_date, fee FROM loans")
    
    return cursor.fetchall()

# function to view all members
def view_members(cursor):
    cursor.execute("SELECT * FROM members") # all members will be shown
    return cursor.fetchall() # returns all members as a list


def update_book(cursor, book_id, title=None, author=None, quantity=None):
    try:
        # Convert and validate book_id
        book_id = int(book_id)
        if book_id <= 0:
            logging.warning(f"Invalid Book ID: {book_id} (must be positive).")
            return False, "Book ID must be a positive number."        
        fields = [] # information stored in lists to keep track of what has been input
        values = []        
        if title:
            fields.append("title = ?")
            values.append(title)
        if author:
            fields.append("author = ?")
            values.append(author)
        if quantity is not None:  # allow updating quantity to 0
            quantity = int(quantity)  # ensure quantity is an integer
            if quantity < 0:
                logging.warning(f"Invalid quantity: {quantity} for Book ID {book_id}")
                return False, "Quantity cannot be negative."
            fields.append("quantity = ?")
            values.append(quantity)
        if fields:
            # check if the book exists
            cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
            if cursor.fetchone():
                query = f"UPDATE books SET {', '.join(fields)} WHERE id = ?"
                values.append(book_id)
                cursor.execute(query, values)
                cursor.connection.commit()
                logging.info(f"Book ID {book_id} updated successfully.")
                return True, f"Book ID {book_id} updated successfully."
            else:
                logging.warning(f"Book ID {book_id} not found.")
                return False, f"Book ID {book_id} does not exist."
        else:
            return False, "No fields provided to update."
    except ValueError:
        logging.error(f"Invalid book ID format: {book_id}")
        return False, "Please enter a valid number for Book ID."
    except sqlite3.Error as e:
        logging.error(f"Database error while updating book: {e}")
        return False, f"Error updating book: {e}"

def update_member(cursor, member_id, name=None, contact_info=None):
    try:
        # convert and validate member_id
        member_id = int(member_id)
        if member_id <= 0:
            logging.warning(f"Invalid Member ID: {member_id} (must be positive).")
            return False, "Member ID must be a positive number."
        fields = []
        values = []
        if name:
            fields.append("name = ?")
            values.append(name)
        if contact_info:
            fields.append("contact_info = ?")
            values.append(contact_info)
        if fields:
            # check if member exists
            cursor.execute("SELECT id FROM members WHERE id = ?", (member_id,))
            if cursor.fetchone():
                query = f"UPDATE members SET {', '.join(fields)} WHERE id = ?"
                values.append(member_id)
                cursor.execute(query, values)
                cursor.connection.commit()
                logging.info(f"Member ID {member_id} updated successfully.")
                return True, f"Member ID {member_id} updated successfully."
            else:
                logging.warning(f"Member ID {member_id} not found.")
                return False, f"Member ID {member_id} does not exist."
        else:
            return False, "No fields provided to update."
    except ValueError:
        logging.error(f"Invalid member ID format: {member_id}")
        return False, "Please enter a valid number for Member ID."
    except sqlite3.Error as e:
        logging.error(f"Database error while updating member: {e}")
        return False, f"Error updating member: {e}"

# Function to validate the email format
def is_valid_email(email):
    email_validation = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$' # input validation to make sure the email follows a set appearance (including @)
    return re.match(email_validation, email) is not None # if matches the format it will be true, if not then it will be none

def register_admin(cursor, username, password):
    try:
        cursor.execute("INSERT INTO admins (username, password) VALUES (?, ?)", (username, password)) # insert new username and password to admins table
        cursor.connection.commit() # save changes to database
        return True # showing success
    except sqlite3.Error as e:
        print(f"Error registering admin: {e}") # print error message if error
        return False # showing failure while registering

def admin_login(cursor, username, password):
    cursor.execute("SELECT * FROM admins WHERE username = ? AND password = ?", (username, password)) # query to see if username and password match an admin record
    result = cursor.fetchone() # get result of query
    return result is not None # Return true if a matching admin is found, otherwise return false

def save_data_to_json(cursor):    
    cursor.execute("SELECT id, title, author, quantity FROM books")#Fetch all book records
    books = [{"id": row[0], "title": row[1], "author": row[2], "quantity": row[3]} for row in cursor.fetchall()]
    cursor.execute("SELECT id, name, contact_info FROM members")#Fetch all member records
    members = [{"id": row[0], "name": row[1], "contact_info": row[2]} for row in cursor.fetchall()]   
    cursor.execute("SELECT id, book_id, member_id, loan_date, return_date, fee FROM loans")#Fetch all loan records
    loans = [{"id": row[0], "book_id": row[1], "member_id": row[2], "loan_date": row[3], "return_date": row[4], "fee": row[5]} for row in cursor.fetchall()]   
    cursor.execute ("SELECT id, username, password FROM admins")#Fetch all admin records
    admins = [{"id": row[0], "username": row[1], "password": row[2]} for row in cursor.fetchall()]
    data = {# Combine data into a dictionary
        "books": books,
        "members": members,
        "loans": loans,
        "admins": admins
        }
    # Write data to JSON file
    with open("library_data.json", "w") as file: # w to show that the file is for writing
        json.dump(data, file, indent=4)
    print("Data successfully saved to JSON.") # debugging to see if data has succesfully saved

def create_window():# Creating the window layout
    layout = [ #defining layout for window
        [sg.TabGroup([[sg.Tab('Admin', [ # creating two tab groups called admin and member including button functionalites for both member and admin actions
            [sg.Text('Admin Interface', font=("Aptos Black", 16), expand_x=True, justification='center')],
            [sg.Button('Add Book', font=("Congenial", 12)), sg.Button('Remove Book', font=("Congenial", 12)), sg.Button('Update Book', font=("Congenial", 12)), sg.Button('View All Books', font=("Congenial", 12))],
            [sg.Button('Add Member', font=("Congenial", 12)), sg.Button('Remove Member', font=("Congenial", 12)), sg.Button('Update Member', font=("Congenial", 12))],
            [sg.Button('View All Loans', font=("Congenial", 12)), sg.Button('View All Members', font=("Congenial", 12))],
            [sg.Multiline(size=(60, 10), key='-ADMIN_OUTPUT-', disabled=True, font=("Congenial", 12))] #textbox for output actions
        ]), sg.Tab('Member', [
            [sg.Text('Member Interface', font=("Aptos Black", 16), expand_x=True, justification='center')],
            [sg.Button('Login', font=("Congenial", 12))],
            [sg.Button('View Available Books', font=("Congenial", 12))],
            [sg.Button('Borrow Book', font=("Congenial", 12))], # borrow book button
            [sg.Button('Return Book', font=("Congenial", 12))], # return book button
            [sg.Button('View My Loans', font=("Congenial", 12))], # view all loans button
            [sg.Multiline(size=(60, 10), key='-MEMBER_OUTPUT-', disabled=True, font=("Congenial", 12))] #textbox for output actions
        ])]])]
    ]
    return sg.Window('Library Management System', layout,) #return pysimple gui with defined layout

def update_loans_table(cursor):
    cursor.execute("PRAGMA table_info(loans)")
    columns = [col[1] for col in cursor.fetchall()]    
#     if "fee" not in columns:
#         cursor.execute("ALTER TABLE loans ADD COLUMN fee REAL DEFAULT 0.0")
#         cursor.connection.commit()
#         print("Database updated: 'fee' column added to loans table.") #sql code to add the fee column to loan table to store loan information
# #

#Main loop

#Configure the logging
logging.basicConfig(filename='library_system.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    connection, cursor = connect_to_db()
    update_loans_table(cursor)

    #Step 1: Admin login window
    login_layout = [
        [sg.Text('Admin Login', font=("Aptos Black", 16), expand_x=True, justification='center')],
        [sg.Text('Username:', font=("Congenial", 12)), sg.InputText(key='-USERNAME-', font=("Congenial", 12))],
        [sg.Text('Password:', font=("Congenial", 12)), sg.InputText(key='-PASSWORD-', font=("Congenial", 12), password_char='*')],
        [sg.Button('Login', font=("Congenial", 12)), sg.Button('Register', font=("Congenial", 12))],
        [sg.Text('', key='-ERROR-', text_color='red', font=("Congenial", 12))]
    ]    
    login_window = sg.Window('Admin Login', login_layout, modal=True) # layout window for the admin login

    # login window for the admin
    while True:
        event, values = login_window.read()

        if event == sg.WINDOW_CLOSED:
            login_window.close()
            connection.close()
            return  # Exit if the user closes the login window

        if event == 'Login':
            username = values['-USERNAME-'] # this even stores the username aand password and variables where they are checked in the databse to verify
            password = values['-PASSWORD-']
            if admin_login(cursor, username, password):
                login_window.close()  # Close the login window upon successful login
                logging.info(f"Admin {username} logged in successfully.")
                break  # Proceed to the main library system window
            else:
                logging.warning(f"Failed login attempt for username: {username}")
                login_window['-ERROR-'].update("Invalid username or password. Please try again.")  # update the page to show error message

        elif event == 'Register': # register button fucntionality           
            register_layout = [ #open the registration window
                [sg.Text('Register New Admin', font=("Congenial", 16), expand_x=True, justification='center')],
                [sg.Text('New Username:', font=("Congenial", 12)), sg.InputText(key='-NEW_USERNAME-', font=("Congenial", 12))],
                [sg.Text('New Password:', font=("Congenial", 12)), sg.InputText(key='-NEW_PASSWORD-', font=("Congenial", 12), password_char='*')],
                [sg.Button('Register', font=("Congenial", 12)), sg.Button('Cancel', font=("Congenial", 12))],
                [sg.Text('', key='-REGISTER_ERROR-', text_color='red', font=("Congenial", 12))]
            ]            
            register_window = sg.Window('Register New Admin', register_layout, modal=True) # defined layout usage as above

            # Step 3: Handle registration form submission
            while True:
                reg_event, reg_values = register_window.read()
                if reg_event == sg.WINDOW_CLOSED or reg_event == 'Cancel':
                    register_window.close() # if window is xed out or cancel is clicked the loop will break out and close
                    break
                if reg_event == 'Register':
                    new_username = reg_values['-NEW_USERNAME-']
                    new_password = reg_values['-NEW_PASSWORD-']     #this event stores new values in the databse to add new admins
                    if new_username and new_password:
                        if register_admin(cursor, new_username, new_password):
                            sg.popup('Admin registered successfully! You can now log in.')
                            logging.info(f"New admin registered with username: {new_username}")
                            register_window.close()
                            break  # Close registration window and return to login screen
                        else:
                            register_window['-REGISTER_ERROR-'].update("Error registering admin. Try again.")
                    else:
                        register_window['-REGISTER_ERROR-'].update("Both fields are required.") # error handling
    
    #if login is successful the librabry system will be shown
    window = create_window()  #calling the window function

    logged_in_member_id = None  # Variable to store the logged-in Member ID

    # Main event loop for the Library System
    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED:
            break
        # Admin actions
        elif event == 'Add Book': # functionality for the add book button
            title = sg.popup_get_text("Please Enter Book Title:") # when the button is clicked the title will be taken from the input in the pop up
            if not title: # if no title
                sg.popup("Book Title Required!", title="Error") # if nothing is inout there will be an error saying you must add a title
                continue            
            author = sg.popup_get_text("Enter Book Author:")
            if not author:
                sg.popup("Book Author Required!", title="Error") # same logic used for author
                continue            
            quantity = sg.popup_get_text("Enter Book Quantity (numbers only):") # # same logic for qauntity
            if not quantity or not quantity.isdigit():
                sg.popup("Please input a number!", title="Error")
                continue            
            add_book(cursor, title, author, int(quantity)) # book will be added using the input being stored as cvariables from the pop up
            logging.info(f"Book added: {title} by {author}, Quantity: {quantity}")  # logging the inputted book
            window['-ADMIN_OUTPUT-'].update("Book added successfully.")# message will pop up in the admin window saying book has been added successfully
        
        elif event == 'Remove Book': # remove book button functionality
            book_id = sg.popup_get_text("Enter Book ID to Remove:") # book id is stored as a vvariable, information is received from the pop up
            if book_id and is_valid_book:
                try:  # Validate book ID
                    book_id = int(book_id)
                    if remove_book(cursor, book_id): # if the id given is in the databse it will be removed after being checked 
                        logging.info(f"Book ID {book_id} removed successfully.") #  information will be stored in a logging file
                        window['-ADMIN_OUTPUT-'].update(f"Book ID {book_id} removed successfully.") # message pops up in the text boxc saying it has been removed for admin to see
                    else:
                        logging.warning(f"Invalid Book ID: {book_id} attempted to remove.") # error handling for if there is an incorrect input
                        window['-ADMIN_OUTPUT-'].update(f"Book ID {book_id} does not exist.") # message pop up
                except ValueError:
                    window['-ADMIN_OUTPUT-'].update(f"Please enter a valid number for Member ID. {book_id}")
                    logging.error(f"Invalid input for Book ID: {book_id}")

        elif event == 'Remove Member':
            member_id = sg.popup_get_text("Enter Member ID to Remove:")
            if member_id and is_valid_member:  # memeber id stored as variable, inforation taken from pop up and checked in database
                try:
                    member_id = int(member_id) #making member_id an integer as that is what it is in the databse
                    if remove_member(cursor, member_id):
                        window['-ADMIN_OUTPUT-'].update(f"Member ID {member_id} removed successfully.") # upon successful removal receive this message
                        logging.info(f"Member ID {member_id} removed successfully.") #  information will be stored in a logging file
                    else:
                        window['-ADMIN_OUTPUT-'].update(f"Member ID {member_id} does not exist.") #
                        logging.warning(f"Invalid Member ID: {member_id} attempted to remove.") # error handling for if there is an incorrect input
                except ValueError:
                    # Handle case where user enters non-integer input
                    window['-ADMIN_OUTPUT-'].update(f"Please enter a valid number for Member ID. {member_id}")
                    logging.error(f"Invalid input for Member ID: {member_id}")

        elif event == 'Add Member': # add memeber button functionality
            name = sg.popup_get_text("PLease Enter Member Name:") # name is stored as a variable 
            if not name: # is nothing is inout an error message will pop up saying it is required
                sg.popup("Member Name is Required!", title="Error")
                continue # can successfully continue inputting member details

            contact_info = sg.popup_get_text ("Please Enter Member Email:") # contact information stored as a variable
            if not contact_info or not is_valid_email(contact_info): # uses the valid email function to make sure it follows email rules like having an @ sign
                sg.popup("Valid Email is Required!", title="Error") #error message relayed
                continue # same logic

            #if all the field inputs are valid it will then be added
            member_id = add_member(cursor, name, contact_info) # using the stored inputs as variables
            logging.info(f"Member added: {name}, Contact Info: {contact_info}") # added to the log file to kstore the information
            window['-ADMIN_OUTPUT-'].update(f"Member added successfully. Name: {name} Member ID: {member_id}") # information is displayed in the text box saying the person has been added showing their name and their memeber id

        elif event == 'Update Book':  # Update book button functionality
            book_id = sg.popup_get_text("Enter Book ID to Update:")  # Get book ID input
            if book_id: # if book id given
                try:
                    book_id = int(book_id)  # Convert input to integer
                    title = sg.popup_get_text("Enter new Title (or leave blank):") #stored as variable if input
                    author = sg.popup_get_text("Enter new Author (or leave blank):") #^^
                    quantity = sg.popup_get_text("Enter new Quantity (or leave blank):") # ^^

                    # Convert quantity only if user provided a value
                    quantity = int(quantity) if quantity else None

                    success, message = update_book(cursor, book_id, title, author, quantity) # message on success
                    window['-ADMIN_OUTPUT-'].update(message) # message in teh multiline
                    if success:
                        logging.info(message) # loggged success
                    else:
                        logging.warning(message)
                except ValueError:
                    logging.error(f"Invalid input for Book ID: {book_id}") # error handling for wrong value given
                    window['-ADMIN_OUTPUT-'].update("Please enter a valid number for Book ID.")

        elif event == 'View All Loans':
            loans = view_loans(cursor)
            table_data = [[loan[0], loan[1], loan[2], loan[3], loan[4] or "Not Returned", f"£{loan[5]:.2f}"]#Convert loan data into a list of lists
                        for loan in loans]
            headers = ["Loan ID", "Book ID", "Member ID", "Loan Date (YYYY-MM-DD)", "Return Date (YYYY-MM-DD)", "Fee"]#Define column headers
            layout = [[sg.Table(values=table_data, # Define table layout
                                headings=headers,
                                auto_size_columns=True,  # Automatically adjust columns
                                justification='left',
                                num_rows=min(10, len(table_data)),  # Show up to 10 rows
                                key='-TABLE-',
                                enable_events=True)]]
            table_window = sg.Window("Library Loans", layout, modal=True)# Create a pop-up table window
            while True:# Event loop for handling table interactions
                event, values = table_window.read()
                if event == sg.WINDOW_CLOSED:
                    break  # Close table when user exits
            table_window.close()
            
        elif event == 'View All Books':
            books = display_books(cursor) # storing the return of the query executed in the function as a variable
            table_data = [[book[0], book[1], book[2], book[3]] for book in books]#convert book data into a list for table
            headers = ["ID", "Title", "Author", "Quantity"]#define column headers
            layout = [[sg.Table(values=table_data,#create a table window
                                headings=headers,
                                auto_size_columns=True, # Able to resize columns
                                justification='left',
                                num_rows=min(10, len(table_data)),  # Show max 10 rows
                                key='-TABLE-',
                                enable_events=True,
                                expand_x=True,
                                expand_y=True)]]
            table_window = sg.Window("Library Books", layout, modal=True) # creates a pop up to show the table
            while True:# Event loop for the table window
                event, values = table_window.read()
                if event == sg.WINDOW_CLOSED:
                    break  # Close the table window when done
            table_window.close()
        
        elif event == 'View All Members':  
            members = view_members(cursor) # storing the return of the query executed in the function as a variable
            table_data = [[member[0], member[1], member[2]] for member in members] #convert member data into a list for table
            headers = ["ID", "Name", "Contact Info"] # define colum headers
            layout = [[sg.Table(values=table_data,
                                headings=headers,
                                auto_size_columns=True, # able to resize columns
                                justification='left', 
                                num_rows=min(10, len(table_data)), # MAx 10 rows
                                key='-TABLE-',
                                enable_events=True,
                                expand_x=True,
                                expand_y=True)]]
            table_window = sg.Window("Library Members", layout, modal=True) # pop up to show table
            while True: # While loop 
                event, values = table_window.read() # reading events for interaction
                if event == sg.WINDOW_CLOSED: #close table when user closes
                    break
            table_window.close()    

        elif event == 'Update Member':  # Update member button functionality
            member_id = sg.popup_get_text("Enter Member ID to Update:")  # Get member ID input fro pop up text
            if member_id: # if there is a member id given
                try:
                    member_id = int(member_id)  # Convert input to integer
                    name = sg.popup_get_text("Enter new Name (or leave blank):") # if name given it will be stored as a variable
                    contact_info = sg.popup_get_text("Enter new Contact Info (or leave blank):") # if email given it will be stored as a variable

                    success, message = update_member(cursor, member_id, name, contact_info) # displays a success message saying member has been updated
                    window['-ADMIN_OUTPUT-'].update(message)
                    if success:
                        logging.info(message) # logging the success
                    else:
                        logging.warning(message) # if no success, a different message will appear
                except ValueError:
                    logging.error(f"Invalid input for Member ID: {member_id}") # letting you know the error for the input
                    window['-ADMIN_OUTPUT-'].update("Please enter a valid number for Member ID.") #message pop up
                    
        # Member functionality
        elif event == 'Login': # login button functionality
            member_id = sg.popup_get_text("Enter Member ID:") # storing the member id as a variable
            if member_id: # checking if the member id is in database
                cursor.execute("SELECT name FROM members WHERE id = ?", (member_id,)) # finding name for related member id given
                member = cursor.fetchone()
                if member:
                    name = member[0] # based on the id given their name will be given
                    logged_in_member_id = int(member_id)  # Store the Member ID after login
                    logging.info(f"Member {name} logged in successfully.") # greet user with their name, which was got from the database
                    sg.popup(f"Welcome, {name}!") # login message
                    window['-MEMBER_OUTPUT-'].update(f"Welcome, {name}") # message shown in the admin window
                else:
                    logging.warning(f"Invalid Member ID: {member_id} attempted to log in.") # if no member id found there is an error
                    window['-MEMBER_OUTPUT-'].update("Invalid Member ID.") # message relayed in the text box
            else:
                logging.warning("Member attempted to log in with empty Member ID.") #error handling for empty field
                window['-MEMBER_OUTPUT-'].update("Please enter your Member ID.") # message popping up saying you must use a enter an ID

        elif event == 'Return Book': # return book button functionality
            if logged_in_member_id: # storing the logged in member id
                loan_id = sg.popup_get_text("Enter Loan ID:") # pop up to get information to store as a variable
                if loan_id: # checking if loan id is provided
                    return_date = sg.popup_get_text("Enter Return Date (YYYY-MM-DD):") # takes input of date with specified format needed
                    if return_date: # checking the date is provided
                        fine, message = return_book(cursor, loan_id, return_date) # call return book function with stored variables
                        if fine is not None: # if return was successful
                            logging.info(f"Book with Loan ID {loan_id} returned successfully") # storing the return information
                            window['-MEMBER_OUTPUT-'].update(message) # displaying success message with any fine information
                        else:
                            logging.warning(f"Failed return attempt for Loan ID {loan_id}: {message}") # stores the failure information
                            window['-MEMBER_OUTPUT-'].update(message) # displays specific error message in text box
                    else:
                        window['-MEMBER_OUTPUT-'].update("Please enter a return date.") # error handling for empty date field
                else:
                    window['-MEMBER_OUTPUT-'].update("Please enter Loan ID.") # error handling for empty loan id field
            else:
                window['-MEMBER_OUTPUT-'].update("Please log in first.") # error handling for not being logged in

        elif event == 'View Available Books':
            books = display_books(cursor) # storing the return of the query executed in the function as a variable
            table_data = [[book[0], book[1], book[2], book[3]] for book in books]#convert book data into a list for table
            headers = ["ID", "Title", "Author", "Quantity"]#define column headers
            layout = [[sg.Table(values=table_data,#create a table window
                                headings=headers,
                                auto_size_columns=True, # Able to resize columns
                                justification='left',
                                num_rows=min(10, len(table_data)),  # Show max 10 rows
                                key='-TABLE-',
                                enable_events=True,
                                expand_x=True,
                                expand_y=True)]]
            table_window = sg.Window("Library Books", layout, modal=True) # creates a pop up to show the table
            while True:# Event loop for the table window
                event, values = table_window.read()
                if event == sg.WINDOW_CLOSED:
                    break  # Close the table window when done
            table_window.close()

        elif event == 'Borrow Book': # borrow book button functionality
            if logged_in_member_id: # using the stored member id 
                book_id = sg.popup_get_text("Enter Book ID to Borrow:") # storing the information as a variable from pop up
                if book_id: # if book id is provided
                    success, message = borrow_book(cursor, book_id, logged_in_member_id) # call borrow book function with stored variables
                    if success: # if successful
                        logging.info(f"Member ID {logged_in_member_id} borrowed Book ID {book_id} successfully.") # storing the successful information
                        window['-MEMBER_OUTPUT-'].update(message) # displays success message in text box
                    else:
                        logging.warning(f"Member ID {logged_in_member_id} failed to borrow Book ID {book_id}: {message}") # stores the failure information
                        window['-MEMBER_OUTPUT-'].update(message) # displays specific error message in text box
                else:
                    window['-MEMBER_OUTPUT-'].update("Please enter a Book ID.") # error handling for empty field
            else:
                window['-MEMBER_OUTPUT-'].update("Please log in first.") # error handling for not being logged in
        
        elif event == 'View My Loans':
            if logged_in_member_id:
                loans = view_loans(cursor, logged_in_member_id)                                
                table_data = [[loan[0], loan[1], loan[2], loan[3] or "Not Returned", f"£{loan[4]:.2f}"]
                            for loan in loans]# Convert loan data into a list of lists for the table                
                headers = ["Loan ID", "Book ID", "Loan Date", "Return Date", "Fee"]# Define column headers                
                layout = [[sg.Table(values=table_data,# Create table layout
                                    headings=headers,
                                    auto_size_columns=True,
                                    justification='left',
                                    num_rows=min(10, len(table_data)),  # Show up to 10 rows
                                    key='-TABLE-',
                                    enable_events=True,
                                    expand_x=True,
                                    expand_y=True)]]                
                table_window = sg.Window("My Loans", layout, modal=True)# Create a pop-up table window
                while True:# Event loop for handling table interactions
                    event, values = table_window.read()
                    if event == sg.WINDOW_CLOSED:
                        break  # Close table when user exits
                table_window.close()
            else:
                window['-MEMBER_OUTPUT-'].update("Please log in first.")
            
    save_data_to_json(cursor) # saving information to a file which can be used as a back up upon closing
    window.close()
    connection.close()

if __name__ == '__main__':
    main()
