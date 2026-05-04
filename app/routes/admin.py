from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.payment import AseRegistry, AccountWalletMapping
import bcrypt

router = APIRouter(prefix="/admin", tags=["admin"])


# ── ASE Management ─────────────────────────────────────────

@router.post("/ases", status_code=status.HTTP_201_CREATED)
def register_ase(
    ase_name: str,
    api_key: str,
    max_connections: int = 50,
    frame_length_type: int = 2,
    db: Session = Depends(get_db),
):
    """Register a new ASE with hashed API key."""
    if frame_length_type not in (2, 4):
        raise HTTPException(status_code=400, detail="frame_length_type must be 2 or 4")

    existing = db.query(AseRegistry).filter(AseRegistry.ase_name == ase_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"ASE '{ase_name}' already registered")

    api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()
    ase = AseRegistry(
        ase_name=ase_name,
        api_key_hash=api_key_hash,
        active=True,
        max_connections=max_connections,
        frame_length_type=frame_length_type,
    )
    db.add(ase)
    db.commit()
    db.refresh(ase)
    return {"id": ase.id, "ase_name": ase.ase_name, "active": ase.active}


@router.get("/ases")
def list_ases(db: Session = Depends(get_db)):
    """List all registered ASEs."""
    ase_list = db.query(AseRegistry).all()
    return [
        {"id": a.id, "ase_name": a.ase_name, "active": a.active,
         "max_connections": a.max_connections, "frame_length_type": a.frame_length_type}
        for a in ase_list
    ]


@router.patch("/ases/{ase_name}")
def update_ase(
    ase_name: str,
    active: bool = None,
    max_connections: int = None,
    frame_length_type: int = None,
    db: Session = Depends(get_db),
):
    """Update ASE configuration."""
    ase = db.query(AseRegistry).filter(AseRegistry.ase_name == ase_name).first()
    if not ase:
        raise HTTPException(status_code=404, detail="ASE not found")

    if active is not None:
        ase.active = active
    if max_connections is not None:
        ase.max_connections = max_connections
    if frame_length_type is not None:
        if frame_length_type not in (2, 4):
            raise HTTPException(status_code=400, detail="frame_length_type must be 2 or 4")
        ase.frame_length_type = frame_length_type

    db.commit()
    return {"id": ase.id, "ase_name": ase.ase_name, "active": ase.active}


@router.post("/ases/{ase_name}/rotate-key", status_code=status.HTTP_201_CREATED)
def rotate_api_key(
    ase_name: str,
    new_api_key: str,
    db: Session = Depends(get_db),
):
    """Rotate API key for an ASE. Returns new key plaintext (show once!)."""
    ase = db.query(AseRegistry).filter(AseRegistry.ase_name == ase_name).first()
    if not ase:
        raise HTTPException(status_code=404, detail="ASE not found")

    ase.api_key_hash = bcrypt.hashpw(new_api_key.encode(), bcrypt.gensalt()).decode()
    db.commit()
    return {"ase_name": ase.ase_name, "message": "API key rotated. Save the new key — it won't be shown again."}


# ── Account-Wallet Mapping Management ──────────────────────

@router.post("/mappings", status_code=status.HTTP_201_CREATED)
def create_mapping(
    ase_name: str,
    account_number: str,
    wallet_address: str,
    db: Session = Depends(get_db),
):
    """Link an ASE account number to a Rafiki wallet address."""
    existing = (
        db.query(AccountWalletMapping)
        .filter(
            AccountWalletMapping.ase_name == ase_name,
            AccountWalletMapping.account_number == account_number,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Mapping for account '{account_number}' under ASE '{ase_name}' already exists",
        )

    mapping = AccountWalletMapping(
        ase_name=ase_name,
        account_number=account_number,
        wallet_address=wallet_address,
        active=True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return {
        "id": mapping.id,
        "ase_name": mapping.ase_name,
        "account_number": mapping.account_number,
        "wallet_address": mapping.wallet_address,
        "active": mapping.active,
    }


@router.get("/mappings")
def list_mappings(
    ase_name: str = None,
    db: Session = Depends(get_db),
):
    """List account-wallet mappings, optionally filtered by ASE."""
    q = db.query(AccountWalletMapping)
    if ase_name:
        q = q.filter(AccountWalletMapping.ase_name == ase_name)
    mappings = q.all()
    return [
        {
            "id": m.id,
            "ase_name": m.ase_name,
            "account_number": m.account_number,
            "wallet_address": m.wallet_address,
            "active": m.active,
        }
        for m in mappings
    ]


@router.patch("/mappings/{mapping_id}")
def update_mapping(
    mapping_id: int,
    active: bool = None,
    wallet_address: str = None,
    db: Session = Depends(get_db),
):
    """Update an account-wallet mapping."""
    mapping = (
        db.query(AccountWalletMapping)
        .filter(AccountWalletMapping.id == mapping_id)
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    if active is not None:
        mapping.active = active
    if wallet_address is not None:
        mapping.wallet_address = wallet_address

    db.commit()
    return {
        "id": mapping.id,
        "ase_name": mapping.ase_name,
        "account_number": mapping.account_number,
        "wallet_address": mapping.wallet_address,
        "active": mapping.active,
    }
