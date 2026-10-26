package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "kildekode")
public class Kildekode {
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
    @Column(name = "kodetype", nullable = false, length = Integer.MAX_VALUE)
    private String kodetype;

    @NotNull
    @Column(name = "kode", nullable = false, length = Integer.MAX_VALUE)
    private String kode;

    @NotNull
    @Column(name = "navn", nullable = false, length = Integer.MAX_VALUE)
    private String navn;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "sist_sett", nullable = false)
    private OffsetDateTime sistSett;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;


}
