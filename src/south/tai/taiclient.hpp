#include <grpcpp/grpcpp.h>
#include "tai.grpc.pb.h"

#include <memory>
#include <vector>

using grpc::Channel;
using grpc::ClientContext;
using tai::TAI;

class TAIClient {
    public:
        TAIClient(std::shared_ptr<Channel> channel) : stub_(TAI::NewStub(channel)) {}
        int ListModule(std::vector<tai::Module>& modules);
        int ListAttributeMetadata(tai::TAIObjectType type, std::vector<tai::AttributeMetadata>& list);
        int GetAttribute(uint64_t oid, uint64_t attr_id, std::string& value);
        int GetAttributeMetadata(tai::TAIObjectType type, const std::string& name, tai::AttributeMetadata& metadata);
        int SetAttribute(uint64_t oid, tai::TAIObjectType type, const std::string& attr, const std::string& value);
    private:
        std::unique_ptr<TAI::Stub> stub_;
};
