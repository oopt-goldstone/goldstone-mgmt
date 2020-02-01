#include "taiclient.hpp"

int TAIClient::ListModule(std::vector<taish::Module>& modules) {
    taish::ListModuleRequest request;
    ClientContext ctx;
    auto reader = stub_->ListModule(&ctx, request);
    taish::ListModuleResponse response;
    while (reader->Read(&response)) {
        modules.emplace_back(response.module());
    }
    return 0;
}

int TAIClient::ListAttributeMetadata(taish::TAIObjectType type, std::vector<taish::AttributeMetadata>& list) {
    taish::ListAttributeMetadataRequest request;
    request.set_object_type(type);
    ClientContext ctx;
    auto reader = stub_->ListAttributeMetadata(&ctx, request);
    taish::ListAttributeMetadataResponse response;
    while (reader->Read(&response)) {
        list.emplace_back(response.metadata());
    }
    return 0;
}

int TAIClient::GetAttributeMetadata(taish::TAIObjectType type, const std::string& name, taish::AttributeMetadata& metadata) {
    taish::GetAttributeMetadataRequest request;
    request.set_object_type(type);
    request.set_attr_name(name);
    auto option = request.mutable_serialize_option();
    option->set_human(true);
    ClientContext ctx;
    taish::GetAttributeMetadataResponse res;
    auto ret = stub_->GetAttributeMetadata(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
    }
    auto meta = ctx.GetServerTrailingMetadata();
    auto it = meta.find("tai-status-code");
    if ( it != meta.end() ) {
        auto code = std::stoi(std::string(it->second.data()));
        if ( code ) {
            return code;
        }
    }
    metadata = res.metadata();
    return 0;
}

int TAIClient::SetAttribute(uint64_t oid, taish::TAIObjectType type, const std::string& name, const std::string& value) {
    uint64_t attr_id;
    taish::AttributeMetadata metadata;
    if ( GetAttributeMetadata(type, name, metadata) ) {
        return 1;
    }
    attr_id = metadata.attr_id();
    taish::SetAttributeRequest request;
    request.set_oid(oid);
    auto option = request.mutable_serialize_option();
    option->set_human(true);
    option->set_value_only(true);
    option->set_json(true);
    auto attr = request.mutable_attribute();
    attr->set_attr_id(attr_id);
    attr->set_value(value);
    ClientContext ctx;
    taish::SetAttributeResponse res;
    auto ret = stub_->SetAttribute(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
    }
    auto meta = ctx.GetServerTrailingMetadata();
    auto it = meta.find("tai-status-code");
    if ( it != meta.end() ) {
        auto code = std::stoi(std::string(it->second.data()));
        if ( code ) {
            return code;
        }
    }
    return 0;
}

int TAIClient::GetAttribute(uint64_t oid, uint64_t attr_id, std::string& value) {
    taish::GetAttributeRequest request;
    request.set_oid(oid);
    auto option = request.mutable_serialize_option();
    option->set_human(true);
    option->set_value_only(true);
    option->set_json(true);
    auto attr = request.mutable_attribute();
    attr->set_attr_id(attr_id);
    ClientContext ctx;
    taish::GetAttributeResponse res;
    auto ret = stub_->GetAttribute(&ctx, request, &res);
    if ( !ret.ok() ) {
        return 1;
    }
    auto meta = ctx.GetServerTrailingMetadata();
    auto it = meta.find("tai-status-code");
    if ( it != meta.end() ) {
        auto code = std::stoi(std::string(it->second.data()));
        if ( code ) {
            return code;
        }
    }
    value = res.attribute().value();
    return 0;
}
