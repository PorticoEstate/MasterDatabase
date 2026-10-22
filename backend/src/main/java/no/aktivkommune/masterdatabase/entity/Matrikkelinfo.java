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
@Table(name = "matrikkelinfo")
public class Matrikkelinfo {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "bygning_id", nullable = false)
    private Bygning bygning;

    @Size(max = 4)
    @NotNull
    @Column(name = "kommunenr", nullable = false, length = 4)
    private String kommunenr;

    @NotNull
    @Column(name = "gardsnr", nullable = false)
    private Integer gardsnr;

    @NotNull
    @Column(name = "bruksnr", nullable = false)
    private Integer bruksnr;

    @Column(name = "festenr")
    private Integer festenr;

    @Column(name = "seksjonsnr")
    private Integer seksjonsnr;

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
