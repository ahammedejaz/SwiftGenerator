package demo;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.notNullValue;
import static org.hamcrest.Matchers.startsWith;

import io.restassured.RestAssured;
import io.restassured.http.ContentType;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The studio from a regression framework's point of view.
 *
 * <p>The point of these three tests is that a framework gets the <em>raw message</em> and
 * structured findings from one call — there is no scraping, no screen, and no second system
 * to reconcile against. The browser calls exactly these endpoints.
 *
 * <p>Outside development, add {@code .header("X-API-Key", System.getenv("STUDIO_API_KEY"))}.
 */
class RestAssuredDemoTest {

    private static final Path DEMO = Path.of("demo");

    @BeforeAll
    static void configure() {
        RestAssured.baseURI = System.getenv().getOrDefault("API_BASE_URL", "http://127.0.0.1:8000");
    }

    @Test
    void generatesAnMt541ThatMatchesTheRecordedReference() throws Exception {
        String expected = Files.readString(DEMO.resolve("expected/MT541.fin"));

        String fin = given()
                .contentType(ContentType.JSON)
                .body(Files.readString(DEMO.resolve("requests/MT541-generate.json")))
                .when()
                .post("/api/v1/messages/generate")
                .then()
                .statusCode(200)
                .body("valid", equalTo(true))
                .body("outputs.fin", startsWith("{1:F01"))
                .extract()
                .path("outputs.fin");

        // Deterministic: the same inputs always produce the same bytes.
        org.junit.jupiter.api.Assertions.assertEquals(expected, fin);
    }

    @Test
    void generatesIso20022AsAHeaderAndADocument() throws Exception {
        given().contentType(ContentType.JSON)
                .body(Files.readString(DEMO.resolve("requests/sese023-generate.json")))
                .when()
                .post("/api/v1/messages/generate")
                .then()
                .statusCode(200)
                .body("valid", equalTo(true))
                .body("outputs.appHdr", notNullValue())
                .body("outputs.document", notNullValue())
                // The schema layer reports which schema it used; it is never implied.
                .body("validation.layers.find { it.layer == 'XSD' }.state", equalTo("PASSED"));
    }

    @Test
    void reportsWhyARegeneratedMessageDiffersFromTheOriginal() throws Exception {
        given().contentType(ContentType.JSON)
                .body(Files.readString(DEMO.resolve("requests/MT541-diff.json")))
                .when()
                .post("/api/v1/messages/diff")
                .then()
                .statusCode(200)
                // One edit, attributed to the caller, and nothing the studio cannot explain.
                .body("diff.summary.changed", equalTo(1))
                .body("diff.summary.unexplained", equalTo(0))
                .body("diff.summary.dropped", equalTo(0))
                .body("diff.lines.find { it.kind == 'CHANGED' }.reason", equalTo("USER_EDIT"));
    }
}
