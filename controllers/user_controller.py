from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    require_roles,
    verify_password,
)
from models.user import (
    LoginRequest,
    StaffUserCreate,
    StaffUserResponse,
    StaffUserUpdate,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from repositories import staff_repository


router = APIRouter(tags=["authentication"])


@router.post(
    "/api/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
def register_user(user: UserCreate):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS count FROM staff_users")
        if cursor.fetchone()["count"] > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bootstrap registration is closed; ask an admin to create the account",
            )

        password_hash = hash_password(user.password)
        cursor.execute("SELECT id FROM roles WHERE code = 'admin'")
        role = cursor.fetchone()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default admin role is not configured",
            )
        cursor.execute(
            """
            INSERT INTO staff_users(role_id, name, email, password_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (role["id"], user.name, user.email, password_hash),
        )
        db.commit()
        return UserResponse(
            id=cursor.lastrowid,
            name=user.name,
            email=user.email,
            role="admin",
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to register user",
        ) from exc
    finally:
        cursor.close()
        db.close()


@router.post(
    "/api/staff-users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
def create_staff_user(
    staff: StaffUserCreate,
    current_user: dict = Depends(require_roles("admin")),
):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM staff_users WHERE email = %s", (staff.email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        cursor.execute("SELECT id FROM roles WHERE code = %s", (staff.role,))
        role = cursor.fetchone()
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown role",
            )
        cursor.execute(
            """
            INSERT INTO staff_users(role_id, name, email, password_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (role["id"], staff.name, staff.email, hash_password(staff.password)),
        )
        staff_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO audit_logs(
                actor_id, entity_type, entity_id, action, after_data
            ) VALUES (%s, 'staff_user', %s, 'created', JSON_OBJECT('email', %s, 'role', %s))
            """,
            (current_user["id"], str(staff_id), staff.email, staff.role),
        )
        db.commit()
        return UserResponse(
            id=staff_id,
            name=staff.name,
            email=staff.email,
            role=staff.role,
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create staff user",
        ) from exc
    finally:
        cursor.close()
        db.close()


@router.get("/api/staff-users", response_model=list[StaffUserResponse])
def list_staff_users(
    current_user: dict = Depends(require_roles("admin")),
):
    db = get_db()
    try:
        return staff_repository.list_staff_users(db)
    finally:
        db.close()


@router.patch("/api/staff-users/{staff_id}", response_model=StaffUserResponse)
def update_staff_user(
    staff_id: int,
    payload: StaffUserUpdate,
    current_user: dict = Depends(require_roles("admin")),
):
    db = get_db()
    try:
        return staff_repository.update_staff_user(
            db,
            staff_id,
            role=payload.role,
            is_active=payload.is_active,
            actor_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except staff_repository.StaffConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        db.close()


@router.post("/api/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT su.id, su.name, su.email, su.password_hash, su.is_active,
                   r.code AS role
            FROM staff_users su
            JOIN roles r ON r.id = su.role_id
            WHERE su.email = %s
            """,
            (request.email,),
        )
        user = cursor.fetchone()

        if (
            user is None
            or not user["is_active"]
            or not verify_password(request.password, user["password_hash"])
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(
            {
                "sub": str(user["id"]),
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
            }
        )
        return TokenResponse(access_token=token)
    finally:
        cursor.close()
        db.close()


@router.get("/api/users/me", response_model=UserResponse)
def read_current_user(current_user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            """
            SELECT su.id, su.name, su.email, r.code
            FROM staff_users su
            JOIN roles r ON r.id = su.role_id
            WHERE su.id = %s AND su.is_active = TRUE
            """,
            (current_user["id"],),
        )
        user = cursor.fetchone()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return UserResponse(id=user[0], name=user[1], email=user[2], role=user[3])
    finally:
        cursor.close()
        db.close()
