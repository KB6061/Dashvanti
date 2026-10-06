from backend.db import engine
from backend.social_models import SocialChallenge, SocialIdentity

if __name__ == '__main__':
    SocialChallenge.__table__.create(engine, checkfirst=True)
    SocialIdentity.__table__.create(engine, checkfirst=True)
