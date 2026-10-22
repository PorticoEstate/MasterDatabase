package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

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

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "fagsystem_instans_id", nullable = false)
    private FagsystemInstans fagsystemInstans;

    @NotNull
    @Column(name = "ekstern_id", nullable = false, length = Integer.MAX_VALUE)
    private String eksternId;

    @NotNull
    @JoinColumns({
            @JoinColumn(name = "kommune_id",
                    referencedColumnName = "kommune_id",
                    nullable = false),
            @JoinColumn(name = "fagsystem_instans_id",
                    referencedColumnName = "fagsystem_instans_id",
                    nullable = false)})
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private KommuneFagsystemInstan kommuneFagsystemInstans;

    @ManyToOne(fetch = FetchType.LAZY)
    private Bygning bygning;

    @NotNull
    @Column(name = "navn", nullable = false, length = Integer.MAX_VALUE)
    private String navn;

    @ManyToOne(fetch = FetchType.LAZY)
    @OnDelete(action = OnDeleteAction.SET_NULL)
    @JoinColumn(name = "lokaletype_id")
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
