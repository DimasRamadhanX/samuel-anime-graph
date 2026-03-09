from neo4j import GraphDatabase
from core.config import settings

class Neo4jProvider:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI, 
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def get_session(self):
        return self.driver.session()

    def close(self):
        self.driver.close()