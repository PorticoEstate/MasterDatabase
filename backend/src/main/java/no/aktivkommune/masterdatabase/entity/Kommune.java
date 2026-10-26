package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.type.SqlTypes;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.ColumnDefault;

import java.time.OffsetDateTime;

@Getter
@Setter
@Entity
@Table(name = "kommune")
public class Kommune {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @Size(max = 4)
    @NotNull
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(name = "kommunenr", nullable = false, length = 4)
    private String kommunenr;

    @NotNull
    @Column(name = "navn", nullable = false, length = Integer.MAX_VALUE)
    private String navn;

    @Column(name = "fylkesnavn", length = Integer.MAX_VALUE)
    private String fylkesnavn;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;


}
