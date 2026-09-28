from ninja import Router

from api.deps import user_auth
from schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from services import auth_service

router = Router(tags=["auth"])


@router.post("/signup", response=SignupResponse)
def signup(request, body: SignupRequest):
    user_id = auth_service.signup(body.email, body.password, body.name)
    return {"userId": user_id}


@router.post("/login", response=LoginResponse)
def login(request, body: LoginRequest):
    return auth_service.login(body.email, body.password)


@router.post("/logout", auth=user_auth)
def logout(request):
    return {}
