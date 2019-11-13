#include "taiclient.hpp"

int TAIClient::ListModule(std::vector<tai::Module>& modules) {
    tai::ListModuleRequest request;
    ClientContext ctx;
    auto reader = stub_->ListModule(&ctx, request);
    tai::ListModuleResponse response;
    while (reader->Read(&response)) {
        modules.emplace_back(response.module());
    }
    return 0;
}

int TAIClient::GetAttribute(uint64_t oid, uint64_t attr_id, std::string& value) {
    tai::GetAttributeRequest request;
    request.set_oid(oid);
    auto attr = request.mutable_attribute();
    attr->set_attr_id(attr_id);
    ClientContext ctx;
    tai::GetAttributeResponse res;
    auto ret = stub_->GetAttribute(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
    }
    value = res.attribute().value();
    return 0;
}
