from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User


def get_current_user(
    vk_user_id: int, db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user