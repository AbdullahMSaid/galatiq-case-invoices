"""Creates and seeds the mock inventory SQLite database (idempotent;
run with: python -m invoice_agents.db.seed)."""




import sqlite3
from pathlib import Path
DB_PATH = Path("inventory.db")  # Relative path so it creates the file again in the same directory 

INVENTORY_ITEMS = [
    ('WidgetA', 15),
    ('WidgetB', 10),
    ('GadgetX', 5),
    ('FakeItem', 0)
]


# Next function will open the database, create the table, clear out the old data, and insert the seed rows. 
#   Save the changes and then close the database
def seed_database() -> None: 
    conn = sqlite3.connect(DB_PATH) # Connect to the database (creates the file if it doesn't exist)
    cursor = conn.cursor() # Create a cursor object to execute SQL commands
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            item TEXT PRIMARY KEY,
            stock INTEGER
        )
        """   
    ) # Create the inventory table if it doesn't exist 

    cursor.execute("DELETE FROM inventory") # Clear out old data to make seeding idempotent
    cursor.executemany(
        "INSERT INTO inventory (item, stock) VALUES (?, ?)", 
        INVENTORY_ITEMS
        
    ) # This inserts the seed data into the inventory table using executemany for efficiency

    conn.commit() # Save the changes to the database
    conn.close() # Close the connection to the database

    print(f"Seeded database at {DB_PATH} with inventory items: {INVENTORY_ITEMS}")

if __name__ == "__main__":
    seed_database()



