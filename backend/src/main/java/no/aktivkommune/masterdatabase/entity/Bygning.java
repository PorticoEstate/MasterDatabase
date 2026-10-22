package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "bygning")
public class Bygning {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

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

    @NotNull
    @Column(name = "navn", nullable = false, length = Integer.MAX_VALUE)
    private String navn;

    @Column(name = "bydel_navn", length = Integer.MAX_VALUE)
    private String bydelNavn;

    @Column(name = "ekstern_id", length = Integer.MAX_VALUE)
    private String eksternId;

    @Column(name = "bygningsnr")
    private Long bygningsnr;

    @Column(name = "bygningstype", length = Integer.MAX_VALUE)
    private String bygningstype;

    @Column(name = "bra_m2", precision = 12, scale = 2)
    private BigDecimal braM2;

    @Column(name = "geom_wkt", length = Integer.MAX_VALUE)
    private String geomWkt;

    @NotNull
    @ColumnDefault("'ikke_forsokt'")
    @Column(name = "matrikkel_match", nullable = false, length = Integer.MAX_VALUE)
    private String matrikkelMatch;

    @Column(name = "antall_etasjer")
    private Integer antallEtasjer;

	@Transient
    @Column(name = "posisjon", columnDefinition = "geography")
    private Object posisjon;

    @NotNull
    @ColumnDefault("true")
    @Column(name = "aktiv", nullable = false)
    private Boolean aktiv;

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


}
