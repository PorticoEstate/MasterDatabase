package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "adresse")
public class Adresse {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @NotNull
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "bygning_id", nullable = false)
    private Bygning bygning;

    @ManyToOne(fetch = FetchType.LAZY)
    @OnDelete(action = OnDeleteAction.SET_NULL)
    @JoinColumn(name = "gate_id")
    private Gate gate;

    @Column(name = "adressetekst", length = Integer.MAX_VALUE)
    private String adressetekst;

    @Column(name = "husnr")
    private Integer husnr;

    @Column(name = "bokstav", length = Integer.MAX_VALUE)
    private String bokstav;

    @Size(max = 4)
    @Column(name = "postnummer", length = 4)
    private String postnummer;

    @Column(name = "poststed", length = Integer.MAX_VALUE)
    private String poststed;

	@Transient
    @Column(name = "posisjon", columnDefinition = "geography")
    private Object posisjon;

    @NotNull
    @ColumnDefault("'ukjent'")
    @Column(name = "geokoding", nullable = false, length = Integer.MAX_VALUE)
    private String geokoding;

    @NotNull
    @ColumnDefault("false")
    @Column(name = "er_hovedadresse", nullable = false)
    private Boolean erHovedadresse;

    @Column(name = "ekstern_id", length = Integer.MAX_VALUE)
    private String eksternId;

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
