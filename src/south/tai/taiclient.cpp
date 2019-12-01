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

int TAIClient::ListAttributeMetadata(tai::TAIObjectType type, std::vector<tai::AttributeMetadata>& list) {
    tai::ListAttributeMetadataRequest request;
    request.set_object_type(type);
    ClientContext ctx;
    auto reader = stub_->ListAttributeMetadata(&ctx, request);
    tai::ListAttributeMetadataResponse response;
    while (reader->Read(&response)) {
        list.emplace_back(response.metadata());
    }
    return 0;
}

int TAIClient::GetAttributeMetadata(tai::TAIObjectType type, const std::string& name, tai::AttributeMetadata& metadata) {
    tai::GetAttributeMetadataRequest request;
    request.set_object_type(type);
    request.set_attr_name(name);
    ClientContext ctx;
    tai::GetAttributeMetadataResponse res;
    auto ret = stub_->GetAttributeMetadata(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
    }
    metadata = res.metadata();
    return 0;
}

int TAIClient::SetAttribute(uint64_t oid, tai::TAIObjectType type, const std::string& name, const std::string& value) {
    uint64_t attr_id;
    tai::AttributeMetadata metadata;
    if ( GetAttributeMetadata(type, name, metadata) ) {
        return 1;
    }
    attr_id = metadata.attr_id();
    tai::SetAttributeRequest request;
    request.set_oid(oid);
    auto attr = request.mutable_attribute();
    attr->set_attr_id(attr_id);
    attr->set_value(value);
    ClientContext ctx;
    tai::SetAttributeResponse res;
    auto ret = stub_->SetAttribute(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
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
