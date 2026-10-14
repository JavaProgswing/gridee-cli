from tools.gridee_apk_audit import (
    consolidate,
    parse_api_service,
    parse_jadx_api_service,
    parse_jadx_model_fields,
    parse_model_fields,
)


def test_parse_retrofit_methods_and_generic_http():
    code = """
.method public abstract getThings(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;
    .param p1
        .annotation runtime Lretrofit2/http/Query;
            value = "page"
        .end annotation
    .end param
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Lretrofit2/Response<",
            "Ljava/util/List<",
            "Lcom/gridee/parking/data/model/ThingResponse;",
            ">;>;"
        }
    .end annotation
    .annotation runtime Lretrofit2/http/GET;
        value = "api/things"
    .end annotation
.end method
.method public abstract deleteThing(Lcom/gridee/parking/data/model/ThingRequest;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;
    .param p1
        .annotation runtime Lretrofit2/http/Body;
        .end annotation
    .end param
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Lretrofit2/Response<",
            "Ljava/lang/Void;",
            ">;"
        }
    .end annotation
    .annotation runtime Lretrofit2/http/HTTP;
        hasBody = true
        method = "DELETE"
        path = "api/things/{id}"
    .end annotation
.end method
"""
    assert parse_api_service(code) == [
        {
            "method": "GET",
            "route": "/api/things",
            "function": "getThings",
            "query": ["page"],
            "hasBody": False,
            "requestType": "none",
            "responseType": "List<ThingResponse>",
            "models": ["com.gridee.parking.data.model.ThingResponse"],
            "sourceClass": "com.gridee.parking.data.api.ApiService",
        },
        {
            "method": "DELETE",
            "route": "/api/things/{id}",
            "function": "deleteThing",
            "query": [],
            "hasBody": True,
            "requestType": "ThingRequest",
            "responseType": "null",
            "models": ["com.gridee.parking.data.model.ThingRequest"],
            "sourceClass": "com.gridee.parking.data.api.ApiService",
        },
    ]


def test_consolidate_overloads_into_unique_method_route():
    declarations = [
        {
            "method": "GET",
            "route": "/api/things",
            "function": "getThings",
            "query": [],
            "hasBody": False,
            "requestType": "none",
            "responseType": "unknown",
            "models": [],
            "sourceClass": "Api",
        },
        {
            "method": "GET",
            "route": "/api/things",
            "function": "getThingsByType",
            "query": ["type"],
            "hasBody": False,
            "requestType": "none",
            "responseType": "unknown",
            "models": [],
            "sourceClass": "Api",
        },
    ]
    assert consolidate(declarations) == [
        {
            "method": "GET",
            "route": "/api/things",
            "functions": ["getThings", "getThingsByType"],
            "query": ["type"],
            "hasBody": False,
            "requestTypes": ["none"],
            "responseTypes": ["unknown"],
            "models": [],
            "sourceClasses": ["Api"],
        }
    ]


def test_parse_obfuscated_retrofit_annotations_from_175():
    code = """
.method public abstract e(Ljava/lang/String;Ljava/lang/String;IILjh/c;)Ljava/lang/Object;
    .param p2
        .annotation runtime Llj/t;
            value = "status"
        .end annotation
    .end param
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Lij/o0<",
            "Lcom/gridee/parking/data/model/Booking;",
            ">;"
        }
    .end annotation
    .annotation runtime Llj/f;
        value = "api/bookings/{userId}/history/page"
    .end annotation
.end method
.method public abstract k(Ljava/lang/String;Lcom/gridee/parking/data/model/TopUpRequest;Ljh/c;)Ljava/lang/Object;
    .param p2
        .annotation runtime Llj/a;
        .end annotation
    .end param
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Lij/o0<",
            "Lcom/gridee/parking/data/model/TopUpResponse;",
            ">;"
        }
    .end annotation
    .annotation runtime Llj/o;
        value = "api/users/{userId}/wallet/topup"
    .end annotation
.end method
"""
    parsed = parse_api_service(code, "mf.c")
    assert [(item["method"], item["route"]) for item in parsed] == [
        ("GET", "/api/bookings/{userId}/history/page"),
        ("POST", "/api/users/{userId}/wallet/topup"),
    ]
    assert parsed[0]["query"] == ["status"]
    assert parsed[0]["responseType"] == "Booking"
    assert parsed[1]["requestType"] == "TopUpRequest"
    assert parsed[1]["responseType"] == "TopUpResponse"


def test_parse_jadx_obfuscated_api_interface():
    source = '''
public interface c {
    @lj.f("api/bookings/{userId}/history/page")
    Object e(@s("userId") String user, @t("status") String status, @t("page") int page, @t("size") int size, jh.c<? super o0<q>> cVar);

    @o("api/users/{userId}/wallet/topup")
    Object k(@s("userId") String user, @lj.a TopUpRequest request, jh.c<? super o0<TopUpResponse>> cVar);

    @lj.h(hasBody = true, method = "DELETE", path = "api/notifications/tokens")
    Object n(@lj.a DeviceTokenUnregisterRequest request, jh.c<? super o0<Void>> cVar);
}
'''
    parsed = parse_jadx_api_service(source)
    assert [(item["method"], item["route"]) for item in parsed] == [
        ("GET", "/api/bookings/{userId}/history/page"),
        ("POST", "/api/users/{userId}/wallet/topup"),
        ("DELETE", "/api/notifications/tokens"),
    ]
    assert parsed[0]["query"] == ["status", "page", "size"]
    assert parsed[0]["responseType"] == "JsonElement"
    assert parsed[1]["requestType"] == "TopUpRequest"
    assert parsed[2]["requestType"] == "DeviceTokenUnregisterRequest"


def test_parse_jadx_model_field_patterns():
    source = '''
public final class SampleResponse {
    @b("display_name")
    private final String displayName;

    @b(alternate = {"_id"}, value = "id")
    private final String f4066id;

    private final List<Booking> bookings;
    private final double amount;
}
'''
    assert parse_jadx_model_fields(source) == [
        {"name": "display_name", "type": "string"},
        {"name": "id", "type": "string"},
        {"name": "bookings", "type": "List<Booking>"},
        {"name": "amount", "type": "number"},
    ]


def test_parse_serialized_model_field_patterns():
    code = """
# instance fields
.field private final email:Ljava/lang/String;
    .annotation runtime Lcom/google/gson/annotations/SerializedName;
        value = "email_address"
    .end annotation
.end field
.field private final amount:D
# direct methods
"""
    assert parse_model_fields(code) == [
        {"name": "email_address", "type": "string"},
        {"name": "amount", "type": "number"},
    ]
