"""
Simple script to view database contents.
Run: python view_db.py

Make sure Docker is running: docker-compose up -d
"""

from app.database import db, Transaction
from sqlalchemy import text

def view_transactions():
    """Display all transactions in the database."""
    
    # Create session
    session = db.SessionLocal()
    
    try:
        # Query all transactions
        transactions = session.query(Transaction).all()
        
        if not transactions:
            print("No transactions found in database.")
            return
        
        print("=" * 100)
        print(f"Total Transactions: {len(transactions)}")
        print("=" * 100)
        
        for t in transactions:
            print(f"\nID: {t.id}")
            print(f"  MTI: {t.mti}")
            print(f"  STAN: {t.stan}")
            print(f"  RRN: {t.rrn}")
            print(f"  Source Account: {t.source_account}")
            print(f"  Source Coop: {t.source_coop_id}")
            print(f"  Amount: {t.amount} {t.currency}")
            print(f"  Status: {t.status}")
            print(f"  Response Code: {t.response_code}")
            print(f"  Rafiki Payment ID: {t.rafiki_payment_id}")
            print(f"  Created: {t.created_at}")
            print(f"  Updated: {t.updated_at}")
            print("-" * 100)
        
        # Summary stats
        print("\n\nSummary:")
        completed = session.query(Transaction).filter(Transaction.status == "COMPLETED").count()
        failed = session.query(Transaction).filter(Transaction.status == "FAILED").count()
        pending = session.query(Transaction).filter(Transaction.status == "PENDING").count()
        
        print(f"  Completed: {completed}")
        print(f"  Failed: {failed}")
        print(f"  Pending: {pending}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

def view_table_structure():
    """Display the database table structure."""
    print("\n" + "=" * 100)
    print("TABLE STRUCTURE: transactions")
    print("=" * 100)
    
    session = db.SessionLocal()
    try:
        result = session.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'transactions'
            ORDER BY ordinal_position;
        """))
        
        for row in result:
            print(f"{row[0]:<30} {row[1]:<25} Nullable: {row[2]:<5} Default: {row[3]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    print("Payment Middleware - Database Viewer")
    print("=" * 100)
    
    view_table_structure()
    view_transactions()
