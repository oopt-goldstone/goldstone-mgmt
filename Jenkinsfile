pipeline {
  agent any

  parameters {
    string(name: 'DEVICE', defaultValue: '10.10.10.116', description: 'IP address of the test device')
    booleanParam(name: 'FORCE_BUILD_BUILDER', defaultValue: false, description: 'build builder image forcibly')
  }

  stages {
    stage('Setup') {
      steps {
          sh 'env'
          script {
              env.SKIP = 0
              if (env.BRANCH_NAME == 'master' ) {
                  env.DOCKER_REPO = 'nlpldev'
                  env.BUILD_BUILDER = 1
              } else if ( env.BRANCH_NAME.startsWith('PR') ) {
                  env.DOCKER_REPO = 'gs-test'
                  // if sm/, patches/, builder.Dockerfile, build_onlp.sh is updated
                  // build the builder
                  env.BUILD_BUILDER = sh(returnStatus: true, script: "git diff --compact-summary HEAD origin/master | grep 'sm/\\|patches/\\|builder.Dockerfile\\|build_onlp.sh'") ? 0 : 1
              } else {
                  env.SKIP = 1
                  env.BUILD_BUILDER = 0
                  currentBuild.result = 'SUCCESS'
                  echo "no need to build ${env.BRANCH_NAME}"
              }
              if ( params.FORCE_BUILD_BUILDER ) {
                  env.BUILD_BUILDER = 1
              }
          }
          sh 'env'
      }
    }

    stage('Lint') {
      when {
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'apk add --update docker make python2'
        sh 'make tester'
        sh "docker run -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test make lint"
      }
    }

    stage('Build Builder') {
      when {
        environment name: 'BUILD_BUILDER', value: '1'
      }
      steps {
          sh 'make builder'
      }
    }

    stage('Build') {
      when {
        environment name: 'SKIP', value: '0'
      }
      steps {
          sh 'make snmpd'
          sh 'make base-image'
          sh 'make images'
      }
    }

    stage('Load') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'make tester'
        timeout(time: 15, unit: 'MINUTES') {
            sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -e DOCKER_REPO=$DOCKER_REPO -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 -m ci.tools.load ${params.DEVICE}"
        }
      }
    }

    stage('Test') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'make tester'
        timeout(time: 20, unit: 'MINUTES') {
            sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -e DOCKER_REPO=$DOCKER_REPO -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 -m ci.tools.test ${params.DEVICE}"
        }
      }
    }

    stage('Test NETCONF') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'make tester'
        sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -e DOCKER_REPO=$DOCKER_REPO -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 -m ci.tools.test_np2 ${params.DEVICE}"
      }
    }

   stage('Test SNMP') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'make tester'
        sh "docker run -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 -m ci.tools.test_snmp ${params.DEVICE}"
      }
    }
  }

  post {
    always {
      script {
        if ( env.BRANCH_NAME != 'master' ) {
          deleteDir() /* clean up our workspace */
        }
      }
    }
  }

}
