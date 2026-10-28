package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.JoinFormula;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "ressurs")
public class Ressurs {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    // Kun kolonneverdier, ingen assosiasjoner: kolonnene inngår i flere sammensatte
    // fremmednøkler (kommune+instans, bygning+kommune) som databasen håndhever selv.
    @NotNull
    @Column(name = "fagsystem_instans_id", nullable = false)
    private Long fagsystemInstansId;

    @NotNull
    @Column(name = "ekstern_id", nullable = false, length = Integer.MAX_VALUE)
    private String eksternId;

    @NotNull
    @Column(name = "kommune_id", nullable = false)
    private Long kommuneId;

    @Column(name = "bygning_id")
    private Long bygningId;

    @NotNull
    @Column(name = "navn", nullable = false, length = Integer.MAX_VALUE)
    private String navn;

    // Utledet, ikke en kolonne: ressurs_lokaletype er en visning som regnes ut fra
    // ressurs_kildekode og godkjent mapping. Skrivebeskyttet.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinFormula(
        value = "(SELECT rl.lokaletype_id FROM ressurs_lokaletype rl WHERE rl.ressurs_id = id)",
        referencedColumnName = "id")
    private Lokaletype lokaletype;

    @Column(name = "kapasitet")
    private Integer kapasitet;

    @Column(name = "areal_m2", precision = 10, scale = 2)
    private BigDecimal arealM2;

    @Column(name = "beskrivelse", length = Integer.MAX_VALUE)
    private String beskrivelse;

    @NotNull
    @ColumnDefault("true")
    @Column(name = "aktiv", nullable = false)
    private Boolean aktiv;

    @NotNull
    @ColumnDefault("true")
    @Column(name = "bookbar", nullable = false)
    private Boolean bookbar;

    @Column(name = "sist_oppdatert")
    private OffsetDateTime sistOppdatert;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

	@Transient
    @ColumnDefault("to_tsvector('norwegian', ((COALESCE(navn, ''::text) || ' '::text) || COALESCE(beskrivelse, '')))")
    @Column(name = "sokevektor", columnDefinition = "tsvector")
    private Object sokevektor;


}
