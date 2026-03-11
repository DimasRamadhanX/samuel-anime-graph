from core.database import Neo4jProvider
import logging

logger = logging.getLogger("uvicorn")

class GraphService:
    def __init__(self, provider: Neo4jProvider):
        self.provider = provider

    def setup_constraints(self):
        # schema_init
        with self.provider.get_session() as session:
            labels = ["Anime", "Character", "Staff", "VoiceActor", "Studio", "Genre", "Demographic", "Source"]
            for label in labels:
                # Gunakan property 'id' untuk entity, 'name' untuk kategori
                prop = "name" if label in ["Genre", "Demographic", "Source"] else "id"
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
        logger.info("Constraints re-configured.")

    def truncate_database(self):
        # total_factory_reset
        with self.provider.get_session() as session:
            # 1. Hapus semua data kecuali Admin
            session.run("MATCH (n) WHERE NOT 'Admin' IN labels(n) DETACH DELETE n")
            
            # 2. Drop semua constraints & indexes agar bersih total
            res = session.run("SHOW CONSTRAINTS YIELD name")
            for rec in res: session.run(f"DROP CONSTRAINT {rec['name']}")
            
            res = session.run("SHOW INDEXES YIELD name")
            for rec in res: 
                if rec['name'] != 'CONSTRAINT_INDEX': # Hindari drop index sistem
                    try: session.run(f"DROP INDEX {rec['name']}")
                    except: pass
                    
        self.setup_constraints()
        logger.info("Database deep cleaned.")

    def sync_to_neo4j(self, anime_list):
        # strict_data_sync
        with self.provider.get_session() as session:
            for anime in anime_list:
                data = anime if isinstance(anime, dict) else anime.dict()
                tags = data.get('tags') or []
                
                params = {
                    "id": data['id'],
                    "title": data.get('title', {}).get('romaji', 'Unknown'),
                    "score": data.get('averageScore', 0),
                    "year": data.get('startDate', {}).get('year', 0),
                    "source": data.get('source', 'ORIGINAL'),
                    "genres": data.get('genres') or [],
                    "demographics": [t['name'] for t in tags if t.get('category') == 'Demographic'],
                    "studios": [{"id": s['id'], "name": s['name']} for s in data.get('studios', {}).get('nodes', [])],
                    "staff_prod": [{"id": e['node']['id'], "name": e['node']['name']['full'], "role": e.get('role', 'Staff')} 
                                  for e in data.get('staff', {}).get('edges', [])],
                    "characters": data.get('characters', {}).get('edges', [])
                }
                session.execute_write(self._create_graph, params)

    @staticmethod
    def _create_graph(tx, p):
        # final_graph_logic
        query = """
        // 1. Anime & Source
        MERGE (a:Anime {id: $id})
        SET a.title = $title, a.score = $score, a.year = $year
        MERGE (src:Source {name: $source})
        MERGE (a)-[:BASED_ON]->(src)

        // 2. Genre & Demographic
        FOREACH (g IN $genres | MERGE (gen:Genre {name: g}) MERGE (a)-[:HAS_GENRE]->(gen))
        FOREACH (d IN $demographics | MERGE (demo:Demographic {name: d}) MERGE (a)-[:TARGETED_AT]->(demo))

        // 3. Studio
        FOREACH (st IN $studios | 
            MERGE (s:Studio {id: st.id}) SET s.name = st.name 
            MERGE (a)-[:PRODUCED_BY]->(s)
        )

        // 4. Staff Produksi
        FOREACH (stf IN $staff_prod |
            MERGE (s:Staff {id: stf.id}) SET s.name = stf.name
            MERGE (s)-[:WORKED_AT {role: stf.role}]->(a)
        )

        // 5. Character & VoiceActor
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