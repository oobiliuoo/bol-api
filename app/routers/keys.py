from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session
from app.db.crud import create_api_key, get_all_api_keys, delete_api_key, toggle_api_key, get_api_key_by_id
from app.auth.models import APIKeyCreate, APIKeyResponse, APIKeyList, APIKeyReveal

router = APIRouter(prefix="/admin/keys", tags=["API Keys"])


async def get_db():
    async with async_session() as session:
        yield session


@router.post("", response_model=APIKeyResponse)
async def create_key(data: APIKeyCreate, db: AsyncSession = Depends(get_db)):
    """创建新的API Key"""
    raw_key, api_key = await create_api_key(db, data.name)
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        created_at=api_key.created_at.isoformat(),
        key=raw_key  # 仅在创建时返回完整key
    )


@router.get("", response_model=list[APIKeyList])
async def list_keys(db: AsyncSession = Depends(get_db)):
    """列出所有API Key"""
    keys = await get_all_api_keys(db)
    return [
        APIKeyList(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            created_at=k.created_at.isoformat()
        )
        for k in keys
    ]


@router.get("/{key_id}/reveal", response_model=APIKeyReveal)
async def reveal_key(key_id: int, db: AsyncSession = Depends(get_db)):
    """显示完整API Key（需要管理员权限）"""
    api_key = await get_api_key_by_id(db, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    if not api_key.encrypted_key:
        raise HTTPException(status_code=404, detail="Key not stored")
    return APIKeyReveal(id=api_key.id, key=api_key.encrypted_key)


@router.delete("/{key_id}")
async def delete_key(key_id: int, db: AsyncSession = Depends(get_db)):
    """删除API Key"""
    success = await delete_api_key(db, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key not found")
    return {"message": "API Key deleted"}


@router.patch("/{key_id}")
async def toggle_key(key_id: int, is_active: bool, db: AsyncSession = Depends(get_db)):
    """启用/禁用API Key"""
    api_key = await toggle_api_key(db, key_id, is_active)
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    return {"message": f"API Key {'enabled' if is_active else 'disabled'}"}