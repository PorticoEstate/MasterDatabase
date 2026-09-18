# Norwegian Municipality Activity & Facility Data Explorer

A Next.js application for exploring and analyzing booking system data from Norwegian municipalities.

## Features

- **Interactive Data Explorer**: Browse through 450+ unique activities and 666+ unique facilities
- **Advanced Filtering**: Filter by occurrence percentage, municipality, and search terms
- **Detailed Views**: Expandable cards showing complete municipality lists, descriptions, and contact information
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Search**: Instant filtering and sorting capabilities

## Data Source

This application analyzes comprehensive booking system data from 17 Norwegian municipalities:
- Alesund, Alver, Bærum, Bardu, Bergen, Drammen, Eigersund, Kristiansand, Kvam, Larvik, Øygarden, Sandnes, Sola, Stavanger, Suldal, Sunnfjord, Time

## Getting Started

### Development

```bash
# Install dependencies
npm install

# Run the development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

### Docker Deployment

#### Quick Start
```bash
# Build and run with Docker Compose
docker-compose up --build
```

#### Production with Nginx
```bash
# Run with nginx reverse proxy
docker-compose --profile production up --build
```

#### Manual Docker Build
```bash
# Build the image
docker build -t activity-data-explorer .

# Run the container
docker run -p 3000:3000 activity-data-explorer
```

## Usage

### Navigation
- **Activities Tab**: Explore all activities with their occurrence rates across municipalities
- **Facilities Tab**: Browse facilities with location and contact information

### Filtering Options
- **Search**: Find specific activities or facilities by name
- **Min Occurrence**: Filter by how common items are (Universal 100%, Common 75%+, etc.)
- **Municipality**: Show only items from specific municipalities
- **Sort**: Order by occurrence percentage, name, or municipality count

### Detailed Information
Click on any item to expand and see:
- **Activities**: Full municipality list, descriptions, parent relationships
- **Facilities**: Locations, contact information, activity associations

## Architecture

- **Frontend**: Next.js 15 with TypeScript
- **Styling**: CSS Modules (no Tailwind)
- **Data**: Static JSON file served from public directory
- **Deployment**: Docker with optional Nginx reverse proxy

## File Structure

```
data-explorer-app/
├── src/app/
│   ├── page.tsx           # Main application component
│   └── page.module.css    # Styling
├── public/
│   └── comprehensive_analysis_results.json  # Data file
├── Dockerfile             # Container configuration
├── docker-compose.yml     # Multi-container setup
└── nginx.conf            # Reverse proxy configuration
```

## Data Analysis Results

### Activities
- **1 Universal activity** (100%): "Idrett"
- **30 Common activities** (75-99%): Including Bordtennis, Bryting, Dans, Fotball
- **377 Rare activities** (<25%): Municipality-specific activities

### Facilities
- **666 Unique facilities** - All location-specific
- Most facilities appear in only 1-2 municipalities
- Categories include halls, schools, sports facilities, cultural centers

## Development

Built with modern web technologies:
- Next.js 15 with App Router
- TypeScript for type safety
- CSS Modules for styling
- Docker for containerization

## License

This project analyzes public booking system data from Norwegian municipalities for research and development purposes.