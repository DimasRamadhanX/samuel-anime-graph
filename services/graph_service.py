from core.database import Neo4jProvider
import logging

logger = logging.getLogger("uvicorn")

class GraphService:
    def __init__(self, provider: Neo4jProvider):
        self.provider = provider

    def setup_constraints(self):
        """Constraint dasar tanpa basa-basi untuk skema yang sederhana."""
        with self.provider.get_session() as session:
            # ID Unik untuk entitas fisik
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Anime) REQUIRE a.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Character) REQUIRE c.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (v:VoiceActor) REQUIRE v.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Staff) REQUIRE s.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (st:Studio) REQUIRE st.id IS UNIQUE")
            
            # Nama Unik untuk kategori general
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Demographic) REQUIRE d.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Type) REQUIRE t.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (src:Source) REQUIRE src.name IS UNIQUE")
        logger.info("Simple constraints configured.")

    def truncate_database(self):
        """Menghapus SEMUA Node, Edge, dan Property, KECUALI akun Admin."""
        with self.provider.get_session() as session:
            
            # 1. Hapus Semua Data (Node, Edge, Property) kecuali Admin
            session.run("""
                MATCH (n) 
                WHERE NOT 'Admin' IN labels(n) 
                DETACH DELETE n
            """)
            
            # 2. Hapus Semua Constraint Schema
            try:
                constraints = session.run("SHOW CONSTRAINTS YIELD name")
                for record in constraints:
                    session.run(f"DROP CONSTRAINT {record['name']}")
            except Exception:
                pass 
                
        # 3. Pasang ulang constraint yang bersih
        self.setup_constraints()
        logger.info("Semua Node, Edge, dan Property dihapus. Akun Admin dipertahankan.")

    def sync_to_neo4j(self, anime_list):
        """Memformat data dari AniList sebelum dikirim ke Neo4j."""
        with self.provider.get_session() as session:
            for anime in anime_list:
                data = anime if isinstance(anime, dict) else anime.dict()
                
                raw_tags = data.get('tags') or []
                demographics = [t['name'] for t in raw_tags if t.get('category') == 'Demographic']

                # Rapikan data staff agar gampang diakses di Cypher
                all_staff = [
                    {"id": e['node']['id'], "name": e['node']['name']['full'], "role": e.get('role', 'Staff')} 
                    for e in data.get('staff', {}).get('edges', [])
                ]

                params = {
                    "id": data['id'],
                    "title": data.get('title', {}).get('romaji', 'Unknown Title'),
                    "score": data.get('averageScore'),
                    "year": data.get('startDate', {}).get('year'),
                    "source": data.get('source'),
                    "format": data.get('format'),
                    "genres": data.get('genres') or [],
                    "demographics": demographics,
                    "studios": data.get('studios', {}).get('nodes', []),
                    "char_edges": data.get('characters', {}).get('edges', []),
                    "all_staff": all_staff,
                    "relations": data.get('relations', {}).get('edges', [])
                }

                session.execute_write(self._create_simple_graph, params)

    @staticmethod
    def _create_simple_graph(tx, params):
        query = """
        // ---------------------------------------------------------
        // 1. ANIME (Pusat)
        // ---------------------------------------------------------
        MERGE (a:Anime {id: $id})
        SET a.title = $title, 
            a.score = coalesce($score, 0), 
            a.year = coalesce($year, 0)

        // ---------------------------------------------------------
        // 2. KATEGORI (Type & Source)
        // ---------------------------------------------------------
        MERGE (t:Type {name: coalesce($format, 'UNKNOWN')}) 
        MERGE (a)-[:HAS_TYPE]->(t)
        
        MERGE (src:Source {name: coalesce($source, 'ORIGINAL')}) 
        MERGE (a)-[:ADAPTED_FROM]->(src)

        // ---------------------------------------------------------
        // 3. TAGS & STUDIO (Loop simpel)
        // ---------------------------------------------------------
        FOREACH (d IN $demographics | 
            MERGE (demo:Demographic {name: d}) 
            MERGE (a)-[:TARGETS_DEMOGRAPHIC]->(demo)
        )
        FOREACH (g IN $genres | 
            MERGE (gen:Genre {name: g}) 
            MERGE (a)-[:BELONGS_TO_GENRE]->(gen)
        )
        FOREACH (st IN $studios | 
            MERGE (studio:Studio {id: st.id}) 
            SET studio.name = st.name 
            MERGE (a)-[:PRODUCED_BY]->(studio)
        )

        // ---------------------------------------------------------
        // 4. STAFF (1 garis WORKED_ON dengan properti 'role')
        // ---------------------------------------------------------
        FOREACH (stf IN $all_staff |
            MERGE (s:Staff {id: stf.id}) 
            SET s.name = stf.name
            MERGE (s)-[:WORKED_ON {role: stf.role}]->(a)
        )

        // ---------------------------------------------------------
        // 5. CHARACTER & VOICE ACTOR
        // ---------------------------------------------------------
        FOREACH (ch IN $char_edges |
            MERGE (c:Character {id: coalesce(ch.node.id, 0)}) 
            SET c.name = coalesce(ch.node.name.full, 'Unknown')
            
            MERGE (a)-[:INCLUDES_CHARACTER {role: coalesce(ch.role, 'SUPPORTING')}]->(c)
            
            FOREACH (va IN ch.voiceActors |
                MERGE (v:VoiceActor {id: va.id}) 
                SET v.name = va.name.full
                MERGE (v)-[:VOICES]->(c)
            )
        )

        // ---------------------------------------------------------
        // 6. RELASI SESAMA ANIME (Silsilah)
        // ---------------------------------------------------------
        FOREACH (rel IN $relations |
            FOREACH (ignore IN CASE WHEN rel.node.type = 'ANIME' THEN [1] ELSE [] END |
                MERGE (related:Anime {id: rel.node.id})
                ON CREATE SET related.title = coalesce(rel.node.title.romaji, 'Unknown')
                
                // 1 jenis garis RELATED_TO dengan properti 'type' (Sequel/Prequel/dll)
                MERGE (a)-[:RELATED_TO {type: coalesce(rel.relationType, 'OTHER')}]->(related)
            )
        )
        """
        tx.run(query, **params)