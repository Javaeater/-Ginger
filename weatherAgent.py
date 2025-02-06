import python_weather

import asyncio
import os

class WeatherAgent:
    def __init__(self):
        pass
    async def get_weather_today(self, location):
        async with python_weather.Client(unit=python_weather.IMPERIAL) as client:
            weather = await client.get(location)
            return str(weather.temperature)

if __name__ == '__main__':
    agent = WeatherAgent("San Francisco")
    print(asyncio.run(agent.get_weather_today()))