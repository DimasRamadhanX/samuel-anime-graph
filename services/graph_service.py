from core.database import Neo4jProvider
import logging

logger = logging.getLogger("uvicorn")

class GraphService:
    def __init__(self, provider: Neo4jProvider):
        self.provider = provider

    def setup_constraints(self):
        # schema_init
        with self.provider.get_session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Anime) REQUIRE a.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Character) REQUIRE c.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Staff) REQUIRE s.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (v:VoiceActor) REQUIRE v.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (st:Studio) REQUIRE st.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Demographic) REQUIRE d.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (src:Source) REQUIRE src.name IS UNIQUE")
        logger.info("Constraints configured.")

    def truncate_database(self):
        # clear_all
        with self.provider.get_session() as session:
            session.run("MATCH (n) WHERE NOT 'Admin' IN labels(n) DETACH DELETE n")
            try:
                constraints = session.run("SHOW CONSTRAINTS YIELD name")
                for record in constraints: session.run(f"DROP CONSTRAINT {record['name']}")
                indexes = session.run("SHOW INDEXES YIELD name")
                for record in indexes: session.run(f"DROP INDEX {record['name']}")
            except: pass
        self.setup_constraints()
        logger.info("Database reset complete.")

    def sync_to_neo4j(self, anime_list):
        # data_sync
        with self.provider.get_session() as session:
            for anime in anime_list:
                data = anime if isinstance(anime, dict) else anime.dict()
                tags = data.get('tags') or []
                
                # Filter kru produksi
                staff_prod = [
                    {"id": e['node']['id'], "name": e['node']['name']['full'], "role": e.get('role', 'Staff')} 
                    for e in data.get('staff', {}).get('edges', [])
                ]

                params = {
                    "id": data['id'],
                    "title": data.get('title', {}).get('romaji', 'Unknown'),
                    "score": data.get('averageScore', 0),
                    "year": data.get('startDate', {}).get('year', 0),
                    "source": data.get('source', 'ORIGINAL'),
                    "genres": data.get('genres') or [],
                    "demographics": [t['name'] for t in tags if t.get('category') == 'Demographic'],
                    "studios": data.get('studios', {}).get('nodes', []),
                    "characters": data.get('characters', {}).get('edges', []),
                    "staff_prod": staff_prod
                }
                session.execute_write(self._create_graph, params)

    @staticmethod
    def _create_graph(tx, p):
        # graph_query
        query = """
        // 1. Anime & Metadata
        MERGE (a:Anime {id: $id})
        SET a.title = $title, a.score = $score, a.year = $year
        MERGE (src:Source {name: $source})
        MERGE (a)-[:BASED_ON]->(src)

        // 2. Metadata Nodes
        FOREACH (g IN $genres | MERGE (gen:Genre {name: g}) MERGE (a)-[:HAS_GENRE]->(gen))
        FOREACH (d IN $demographics | MERGE (demo:Demographic {name: d}) MERGE (a)-[:TARGETED_AT]->(demo))
        FOREACH (st IN $studios | MERGE (s:Studio {id: st.id}) SET s.name = st.name MERGE (a)-[:PRODUCED_BY]->(s))

        // 3. Produksi Staff (Kru)
        FOREACH (stf IN $staff_prod |
            MERGE (s:Staff {id: stf.id}) SET s.name = stf.name
            MERGE (s)-[:WORKED_AT {role: stf.role}]->(a)
        )

        // 4. Character & Voice Actor (Pemisahan Node)
        FOREACH (ch IN $characters |
            MERGE (c:Character {id: coalesce(ch.node.id, 0)})
            SET c.name = coalesce(ch.node.name.full, 'Unknown')
            MERGE (c)-[:APPEARS_IN {role: coalesce(ch.role, 'SUPPORTING')}]->(a)
            
            FOREACH (va IN ch.voiceActors |
                MERGE (v:VoiceActor {id: va.id}) 
                SET v.name = va.name.full
                MERGE (v)-[:VOICED_BY {language: coalesce(va.languageV2, 'Unknown')}]->(c)
            )
        )
        """
        tx.run(query, **p)