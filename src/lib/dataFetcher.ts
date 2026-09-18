import fs from 'fs/promises';
import path from 'path';
import { MUNICIPALITIES, RawMunicipalityData } from './municipalities';

export interface FetchedMunicipalityData {
  name: string;
  data: RawMunicipalityData | null;
  error: string | null;
}

const DATA_DIR = path.join(process.cwd(), 'data');

export async function fetchMunicipalityData(municipality: { name: string; slug: string }): Promise<FetchedMunicipalityData> {
  try {
    const filePath = path.join(DATA_DIR, `searchdataall-${municipality.slug}.json`);
    const raw = await fs.readFile(filePath, 'utf-8');
    const data = JSON.parse(raw);

    // Validate basic structure
    if (!data.activities || !Array.isArray(data.activities)) {
      throw new Error('Invalid data structure: missing activities array');
    }

    return {
      name: municipality.name,
      data: data as RawMunicipalityData,
      error: null,
    };
  } catch (error) {
    console.error(`Error reading data for ${municipality.name}:`, error);
    return {
      name: municipality.name,
      data: null,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

export async function fetchAllMunicipalitiesData(): Promise<FetchedMunicipalityData[]> {
  console.log(`Reading cached data for ${MUNICIPALITIES.length} municipalities...`);

  const results = await Promise.all(
    MUNICIPALITIES.map(municipality => fetchMunicipalityData(municipality))
  );

  const successful = results.filter(r => r.data !== null).length;
  const failed = results.filter(r => r.data === null).length;

  console.log(`Data loading complete: ${successful} successful, ${failed} failed`);

  return results;
}