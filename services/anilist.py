import httpx
import asyncio

# Query bersih tanpa komentar inline dan menggunakan ENUM sort yang diakui AniList
QUERY = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      total
      hasNextPage
    }
    media(type: ANIME, sort: POPULARITY_DESC) {
      id
      title {
        romaji
        english
      }
      startDate {
        year
      }
      episodes
      averageScore
      format
      source
      genres
      tags {
        name
        category
      }
      studios(isMain: true) {
        nodes {
          id
          name
        }
      }
      staff(perPage: 25) {
        edges {
          role
          node {
            id
            name { full }
          }
        }
      }
      characters(sort: [ROLE, FAVOURITES_DESC]) {
        edges {
          role
          node {
            id
            name { full }
          }
          voiceActors{
            id
            name { full }
            languageV2
          }
        }
      }
      relations {
        edges {
          relationType
          node {
            id
            type
            format
            title { romaji }
          }
        }
      }
    }
  }
}
"""

async def fetch_anime_stream(pages: int):
    url = "https://graphql.anilist.co"
    async with httpx.AsyncClient() as client:
        for page in range(1, pages + 1):
            variables = {"page": page, "perPage": 50}
            try:
                response = await client.post(url, json={"query": QUERY, "variables": variables})
                
                # Handling Rate Limit (Too Many Requests)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    print(f"Rate limited! Sleeping for {retry_after} seconds...")
                    await asyncio.sleep(retry_after)
                    # Mundurkan counter loop untuk mengulang page yang gagal
                    page -= 1 
                    continue 

                # Jika ada error 400 dll, print detail pesan dari GraphQL-nya
                if response.status_code != 200:
                    print(f"GraphQL Error Response (Status {response.status_code}): {response.text}")
                
                response.raise_for_status()
                data = response.json()
                
                anime_list = data.get("data", {}).get("Page", {}).get("media", [])
                if not anime_list:
                    break
                    
                yield anime_list
                
                # Jeda 1 detik agar aman dari ban IP / Rate Limit AniList
                await asyncio.sleep(0.25) 
                
            except Exception as e:
                print(f"Exception on page {page}: {e}")
                break