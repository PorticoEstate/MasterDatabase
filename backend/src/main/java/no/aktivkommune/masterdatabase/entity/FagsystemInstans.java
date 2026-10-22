package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;

import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "fagsystem_instans")
public class FagsystemInstans {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @NotNull
    @Column(name = "kildenokkel", nullable = false, length = Integer.MAX_VALUE)
    private String kildenokkel;

    @NotNull
    @Column(name = "type", nullable = false, length = Integer.MAX_VALUE)
    private String type;

    @Column(name = "navn", length = Integer.MAX_VALUE)
    private String navn;

    @NotNull
    @Column(name = "base_url", nullable = false, length = Integer.MAX_VALUE)
    private String baseUrl;

    @NotNull
    @ColumnDefault("true")
    @Column(name = "aktiv", nullable = false)
    private Boolean aktiv;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;


}
