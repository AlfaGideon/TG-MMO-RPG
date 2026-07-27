import asyncio
from core.database import init_db, async_session
from core.models import AppSetting
from sqlalchemy import select

async def save():
    await init_db()
    async with async_session() as session:
        result = await session.execute(select(AppSetting).where(AppSetting.key == 'bot_token'))
        s = result.scalar_one_or_none()
        if s:
            s.value = '8395291599:AAE-hE-JoCE36JQWjiVNG888xiBh1QNLOrM'
        else:
            s = AppSetting(key='bot_token', value='8395291599:AAE-hE-JoCE36JQWjiVNG888xiBh1QNLOrM')
            session.add(s)
        await session.commit()
        print('Token saved!')

asyncio.run(save())
