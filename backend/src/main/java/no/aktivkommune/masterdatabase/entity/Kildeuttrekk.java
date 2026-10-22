package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

@Getter
@Setter
@Entity
@Table(name = "kildeuttrekk")
public class Kildeuttrekk {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @NotNull
    @Column(name = "kilde", nullable = false, length = Integer.MAX_VALUE)
    private String kilde;

    @NotNull
    @Column(name = "endepunkt", nullable = false, length = Integer.MAX_VALUE)
    private String endepunkt;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "hentet_at", nullable = false)
    private OffsetDateTime hentetAt;

    @Column(name = "http_status")
    private Integer httpStatus;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "payload")
    private Map<String, Object> payload;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;


}
