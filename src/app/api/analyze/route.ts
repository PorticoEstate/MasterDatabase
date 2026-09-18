import { NextResponse } from 'next/server';
import { fetchAllMunicipalitiesData } from '@/lib/dataFetcher';
import { analyzeData } from '@/lib/dataAnalyzer';

export async function GET() {
  try {
    console.log('Starting comprehensive analysis...');
    
    // Fetch all municipality data
    const fetchedData = await fetchAllMunicipalitiesData();
    
    // Analyze the data
    const analysisResult = analyzeData(fetchedData);
    
    console.log(`Analysis complete: ${analysisResult.metadata.successful_fetches} municipalities analyzed`);
    console.log(`Found ${analysisResult.activities.total_unique_activities} activities and ${analysisResult.facilities.total_unique_facilities} facilities`);
    
    return NextResponse.json(analysisResult);
  } catch (error) {
    console.error('Error in analysis API:', error);
    return NextResponse.json(
      { error: 'Failed to fetch and analyze data', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

// Cache for 1 hour in production, but allow revalidation
export const dynamic = 'force-dynamic';
export const revalidate = 3600;