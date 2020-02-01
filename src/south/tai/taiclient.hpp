#include <grpcpp/grpcpp.h>
#include "taish.grpc.pb.h"

#include <memory>
#include <vector>

using grpc::Channel;
using grpc::ClientContext;
using taish::TAI;

class TAIClient {
    public:
        TAIClient(std::shared_ptr<Channel> channel) : stub_(TAI::NewStub(channel)) {}
        int ListModule(std::vector<taish::Module>& modules);
        int ListAttributeMetadata(taish::TAIObjectType type, std::vector<taish::AttributeMetadata>& list);
        int GetAttribute(uint64_t oid, uint64_t attr_id, std::string& value);
        int GetAttributeMetadata(taish::TAIObjectType type, const std::string& name, taish::AttributeMetadata& metadata);
        int SetAttribute(uint64_t oid, taish::TAIObjectType type, const std::string& attr, const std::string& value);
    private:
        std::unique_ptr<TAI::Stub> stub_;
};
