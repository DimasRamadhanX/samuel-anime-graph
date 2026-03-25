from core.database import Neo4jProvider
import logging

logger = logging.getLogger("uvicorn")

class GraphService:
    def __init__(self, provider: Neo4jProvider):
        self.provider = provider

    def setup_constraints(self):
        # schema_init
        with self.provider.get_session() as session:
            labels = ["Anime", "Character", "Staff", "Studio", "Genre", "Demographic", "Source"]
            for label in labels:
                # Gunakan property 'id' untuk entity, 'name' untuk kategori
                prop = "name" if label in ["Genre", "Demographic", "Source"] else "id"
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
        logger.info("Constraints re-configured.")

    def truncate_database(self):
        with self.provider.get_session() as session:
            # 1. Hapus semua data
            session.run("MATCH (n) WHERE NOT 'Admin' IN labels(n) DETACH DELETE n")
            
            # 2. Ambil semua nama constraint dan drop satu per satu
            constraints = session.run("SHOW CONSTRAINTS YIELD name")
            for record in constraints:
                session.run(f"DROP CONSTRAINT {record['name']}")
            
            # 3. Ambil semua nama index dan drop satu per satu
            # Ini penting karena index sering mengikat nama Label di metadata
            indexes = session.run("SHOW INDEXES YIELD name")
            for record in indexes:
                session.run(f"DROP INDEX {record['name']}")

        # Membangun skema baru (hanya label yang kita mau)
        self.setup_constraints()
        logger.info("Database deep cleaned. Metadata reset initiated.")

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
        query = """
        // 1. Node Pusat: Anime & Metadata
        MERGE (a:Anime {id: $id})
        SET a.title = $title, a.score = $score, a.year = $year
        
        MERGE (src:Source {name: $source})
        MERGE (a)-[:BASED_ON]->(src)

        // 2. Metadata (Genre & Demographic)
        FOREACH (g_name IN $genres | 
            MERGE (g:Genre {name: g_name}) 
            MERGE (a)-[:HAS_GENRE]->(g)
        )
        FOREACH (d_name IN $demographics | 
            MERGE (d:Demographic {name: d_name}) 
            MERGE (a)-[:TARGETED_AT]->(d)
        )

        // 3. Studio
        FOREACH (st IN $studios | 
            MERGE (s:Studio {id: st.id}) SET s.name = st.name 
            MERGE (a)-[:PRODUCED_BY]->(s)
        )

        // 4. Kru Produksi (Diproses dalam sub-query agar tidak merusak variabel 'a')
        CALL {
            WITH a
            UNWIND $staff_prod AS stf
            MERGE (s:Staff {id: stf.id}) SET s.name = stf.name
            
            WITH a, s, stf,
            CASE 
                WHEN stf.role CONTAINS 'Director' THEN 'Director'
                WHEN stf.role CONTAINS 'Producer' THEN 'Producer'
                WHEN stf.role CONTAINS 'Script' THEN 'Writer'
                WHEN stf.role CONTAINS 'Animator' THEN 'Animator'
                WHEN stf.role CONTAINS 'Design' THEN 'Designer'
                WHEN stf.role CONTAINS 'Music' OR stf.role CONTAINS 'Composer' THEN 'Musician'
                ELSE stf.role 
            END AS cleanRole
            
            MERGE (s)-[:WORKED_ON {role: cleanRole, original_role: stf.role}]->(a)
            
            WITH s, cleanRole
            UNWIND $studios AS st_info
            MERGE (targetStudio:Studio {id: st_info.id})
            MERGE (s)-[:WORKED_AT {role: cleanRole}]->(targetStudio)
        }

        // 5. Karakter & Pengisi Suara (Juga dalam sub-query)
        CALL {
            WITH a
            UNWIND $characters AS ch
            MERGE (c:Character {id: coalesce(ch.node.id, 0)})
            SET c.name = coalesce(ch.node.name.full, 'Unknown Character')
            MERGE (c)-[:APPEARS_IN {role: coalesce(ch.role, 'SUPPORTING')}]->(a)
            
            WITH a, c, ch
            UNWIND ch.voiceActors AS va
            MERGE (v:Staff {id: va.id}) SET v.name = va.name.full
            
            MERGE (v)-[:VOICES {language: coalesce(va.languageV2, 'Unknown')}]->(c)
            MERGE (v)-[:WORKED_ON {role: 'Voice Actor'}]->(a)

            WITH v
            UNWIND $studios AS st_info
            MERGE (targetStudio:Studio {id: st_info.id})
            MERGE (v)-[:WORKED_AT {role: 'Voice Actor'}]->(targetStudio)
        }
        """
        tx.run(query, **p)