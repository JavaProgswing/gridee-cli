from tools.gridee_apk_audit import consolidate, parse_api_service, parse_model_fields


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
