package no.bergenkommune.masterdb.domain;

/**
 * De tre fasitfilene last_inn.py leser for å kartlegge kildekoder til vårt
 * eget kodeverk (se etl/README.md). Stien er relativ til etl.workdir.
 */
public enum MappingFile {
    LOKALETYPE("etl/lokaletype_mapping/mapping.json"),
    FASILITET("etl/fasilitet_mapping/mapping.json"),
    AKTIVITET("etl/activity_mapping/mapping.json");

    private final String relativePath;

    MappingFile(String relativePath) {
        this.relativePath = relativePath;
    }

    public String relativePath() {
        return relativePath;
    }
}
